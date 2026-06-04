"""Curated kinetic-record schema for external kinetic-law sources."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from fungal_model.core.validators import ValidationResult
from fungal_model.core.value_spec import ValueSpec


KINETIC_RECORD_KIND = "kinetic_record"


class KineticRecordError(ValueError):
    """Raised when a curated kinetic record is invalid."""


@dataclass(frozen=True)
class KineticReaction:
    """Curated reaction metadata for one kinetic record."""

    equation: str
    substrates: tuple[str, ...]
    products: tuple[str, ...]
    external_links: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "KineticReaction":
        return cls(
            equation=str(data.get("equation", "") or ""),
            substrates=tuple(str(item) for item in data.get("substrates", ()) or ()),
            products=tuple(str(item) for item in data.get("products", ()) or ()),
            external_links=deepcopy(dict(data.get("external_links", {}) or {})),
        )

    def validate(self) -> ValidationResult:
        issues: list[dict[str, Any]] = []
        _require_text(issues, "reaction.equation", self.equation)
        if not self.substrates:
            issues.append({"field": "reaction.substrates", "message": "At least one substrate is required."})
        if not self.products:
            issues.append({"field": "reaction.products", "message": "At least one product is required."})
        return _result("kinetic_reaction", issues)

    def to_dict(self) -> dict[str, Any]:
        return {
            "equation": self.equation,
            "substrates": list(self.substrates),
            "products": list(self.products),
            "external_links": deepcopy(dict(self.external_links)),
        }


@dataclass(frozen=True)
class KineticEnzyme:
    """Curated enzyme metadata for one kinetic record."""

    name: str
    ec_number: str
    organism: str | None = None
    enzyme_type: str | None = None
    uniprot_id: str | None = None
    expressed_in: str | None = None

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "KineticEnzyme":
        return cls(
            name=str(data.get("name", "") or ""),
            ec_number=str(data.get("ec_number", "") or ""),
            organism=_optional_str(data.get("organism")),
            enzyme_type=_optional_str(data.get("enzyme_type")),
            uniprot_id=_optional_str(data.get("uniprot_id")),
            expressed_in=_optional_str(data.get("expressed_in")),
        )

    def validate(self) -> ValidationResult:
        issues: list[dict[str, Any]] = []
        _require_text(issues, "enzyme.name", self.name)
        _require_text(issues, "enzyme.ec_number", self.ec_number)
        return _result("kinetic_enzyme", issues)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "ec_number": self.ec_number,
            "organism": self.organism,
            "enzyme_type": self.enzyme_type,
            "uniprot_id": self.uniprot_id,
            "expressed_in": self.expressed_in,
        }


@dataclass(frozen=True)
class KineticLaw:
    """Curated kinetic law metadata."""

    type: str
    formula: str | None = None
    notes: str | None = None

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "KineticLaw":
        return cls(
            type=str(data.get("type", "") or ""),
            formula=_optional_str(data.get("formula")),
            notes=_optional_str(data.get("notes")),
        )

    def validate(self) -> ValidationResult:
        issues: list[dict[str, Any]] = []
        _require_text(issues, "kinetic_law.type", self.type)
        return _result("kinetic_law", issues)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "formula": self.formula,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class KineticParameter:
    """One curated kinetic parameter with original source value and units preserved."""

    symbol: str
    parameter_type: str
    value: float | None
    units: str
    original_value: float | None
    original_units: str
    source_field: str
    original_standard_deviation: float | None = None
    notes: str | None = None

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "KineticParameter":
        if "value" not in data:
            raise KineticRecordError("Kinetic parameter requires explicit value, using null if unknown.")
        return cls(
            symbol=str(data.get("symbol", "") or ""),
            parameter_type=str(data.get("parameter_type", "") or ""),
            value=_optional_float(data.get("value")),
            units=str(data.get("units", "") or ""),
            original_value=_optional_float(data.get("original_value")),
            original_units=str(data.get("original_units", "") or ""),
            source_field=str(data.get("source_field", "") or ""),
            original_standard_deviation=_optional_float(data.get("original_standard_deviation")),
            notes=_optional_str(data.get("notes")),
        )

    def validate(self) -> ValidationResult:
        issues: list[dict[str, Any]] = []
        _require_text(issues, "parameters.symbol", self.symbol)
        _require_text(issues, f"parameters.{self.symbol}.parameter_type", self.parameter_type)
        _require_text(issues, f"parameters.{self.symbol}.units", self.units)
        _require_text(issues, f"parameters.{self.symbol}.original_units", self.original_units)
        _require_text(issues, f"parameters.{self.symbol}.source_field", self.source_field)
        return _result("kinetic_parameter", issues)

    def to_value_spec(self) -> ValueSpec:
        if self.value is None:
            return ValueSpec(
                kind="unknown",
                units=self.units,
                source=self.source_field,
                confidence_level="literature_processed",
                notes=f"{self.symbol} is explicit null in the curated kinetic record.",
            )
        return ValueSpec(
            kind="exact",
            units=self.units,
            value=float(self.value),
            source=self.source_field,
            confidence_level="literature_processed",
            notes=f"{self.symbol} from curated kinetic record.",
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "parameter_type": self.parameter_type,
            "value": self.value,
            "units": self.units,
            "original_value": self.original_value,
            "original_units": self.original_units,
            "source_field": self.source_field,
            "original_standard_deviation": self.original_standard_deviation,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class KineticConditions:
    """Curated assay-condition metadata."""

    temperature: Mapping[str, Any] = field(default_factory=dict)
    ph: Mapping[str, Any] = field(default_factory=dict)
    buffer: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "KineticConditions":
        return cls(
            temperature=deepcopy(dict(data.get("temperature", {}) or {})),
            ph=deepcopy(dict(data.get("ph", {}) or {})),
            buffer=deepcopy(dict(data.get("buffer", {}) or {})),
        )

    def validate(self) -> ValidationResult:
        issues: list[dict[str, Any]] = []
        if self.temperature.get("value") is not None:
            _require_text(issues, "conditions.temperature.units", self.temperature.get("units"))
            if self.temperature.get("original_value") is None:
                issues.append(
                    {
                        "field": "conditions.temperature.original_value",
                        "message": "Converted temperature must preserve original value.",
                    }
                )
            _require_text(
                issues,
                "conditions.temperature.original_units",
                self.temperature.get("original_units"),
            )
        if self.ph.get("value") is not None:
            _require_text(issues, "conditions.ph.units", self.ph.get("units"))
        return _result("kinetic_conditions", issues)

    def to_dict(self) -> dict[str, Any]:
        return {
            "temperature": deepcopy(dict(self.temperature)),
            "ph": deepcopy(dict(self.ph)),
            "buffer": deepcopy(dict(self.buffer)),
        }


@dataclass(frozen=True)
class KineticReference:
    """Publication metadata for a kinetic record."""

    title: str | None = None
    pubmed_id: str | None = None
    doi: str | None = None
    year: int | None = None
    authors: tuple[str, ...] = ()
    journal: str | None = None

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "KineticReference":
        return cls(
            title=_optional_str(data.get("title")),
            pubmed_id=_optional_str(data.get("pubmed_id")),
            doi=_optional_str(data.get("doi")),
            year=_optional_int(data.get("year")),
            authors=tuple(str(item) for item in data.get("authors", ()) or ()),
            journal=_optional_str(data.get("journal")),
        )

    def validate(self) -> ValidationResult:
        return _result("kinetic_reference", [])

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "pubmed_id": self.pubmed_id,
            "doi": self.doi,
            "year": self.year,
            "authors": list(self.authors),
            "journal": self.journal,
        }


@dataclass(frozen=True)
class KineticCuration:
    """Curation metadata for a kinetic record."""

    curated_by: str
    curation_date: str
    method: str
    notes: str

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "KineticCuration":
        return cls(
            curated_by=str(data.get("curated_by", "") or ""),
            curation_date=str(data.get("curation_date", "") or ""),
            method=str(data.get("method", "") or ""),
            notes=str(data.get("notes", "") or ""),
        )

    def validate(self) -> ValidationResult:
        issues: list[dict[str, Any]] = []
        _require_text(issues, "curation.curated_by", self.curated_by)
        _require_text(issues, "curation.curation_date", self.curation_date)
        _require_text(issues, "curation.method", self.method)
        return _result("kinetic_curation", issues)

    def to_dict(self) -> dict[str, Any]:
        return {
            "curated_by": self.curated_by,
            "curation_date": self.curation_date,
            "method": self.method,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class KineticRecord:
    """A curated kinetic-law source record."""

    kind: str
    record_id: str
    source_database: str
    source_reaction_id: str
    source_kinetic_law_id: str
    source_url: str
    reaction: KineticReaction
    enzyme: KineticEnzyme
    kinetic_law: KineticLaw
    parameters: tuple[KineticParameter, ...]
    conditions: KineticConditions
    reference: KineticReference
    curation: KineticCuration

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "KineticRecord":
        return cls(
            kind=str(data.get("kind", "") or ""),
            record_id=str(data.get("record_id", "") or ""),
            source_database=str(data.get("source_database", "") or ""),
            source_reaction_id=str(data.get("source_reaction_id", "") or ""),
            source_kinetic_law_id=str(data.get("source_kinetic_law_id", "") or ""),
            source_url=str(data.get("source_url", "") or ""),
            reaction=KineticReaction.from_mapping(_mapping(data.get("reaction"), "reaction")),
            enzyme=KineticEnzyme.from_mapping(_mapping(data.get("enzyme"), "enzyme")),
            kinetic_law=KineticLaw.from_mapping(_mapping(data.get("kinetic_law"), "kinetic_law")),
            parameters=tuple(
                KineticParameter.from_mapping(_mapping(parameter, "parameters[]"))
                for parameter in data.get("parameters", ()) or ()
            ),
            conditions=KineticConditions.from_mapping(_mapping(data.get("conditions"), "conditions")),
            reference=KineticReference.from_mapping(_mapping(data.get("reference"), "reference")),
            curation=KineticCuration.from_mapping(_mapping(data.get("curation"), "curation")),
        )

    def validate(self) -> ValidationResult:
        issues: list[dict[str, Any]] = []
        if self.kind != KINETIC_RECORD_KIND:
            issues.append({"field": "kind", "message": "KineticRecord kind must be kinetic_record."})
        _require_text(issues, "record_id", self.record_id)
        _require_text(issues, "source_database", self.source_database)
        _require_text(issues, "source_reaction_id", self.source_reaction_id)
        _require_text(issues, "source_kinetic_law_id", self.source_kinetic_law_id)
        _extend_child_issues(issues, self.reaction.validate())
        _extend_child_issues(issues, self.enzyme.validate())
        _extend_child_issues(issues, self.kinetic_law.validate())
        if not self.parameters:
            issues.append({"field": "parameters", "message": "At least one kinetic parameter is required."})
        for parameter in self.parameters:
            _extend_child_issues(issues, parameter.validate())
        _extend_child_issues(issues, self.conditions.validate())
        _extend_child_issues(issues, self.reference.validate())
        _extend_child_issues(issues, self.curation.validate())
        return _result("kinetic_record", issues)

    def require_valid(self) -> "KineticRecord":
        validation = self.validate()
        if not validation.passed:
            raise KineticRecordError(f"{validation.message}: {validation.details['issues']}")
        return self

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "record_id": self.record_id,
            "source_database": self.source_database,
            "source_reaction_id": self.source_reaction_id,
            "source_kinetic_law_id": self.source_kinetic_law_id,
            "source_url": self.source_url,
            "reaction": self.reaction.to_dict(),
            "enzyme": self.enzyme.to_dict(),
            "kinetic_law": self.kinetic_law.to_dict(),
            "parameters": [parameter.to_dict() for parameter in self.parameters],
            "conditions": self.conditions.to_dict(),
            "reference": self.reference.to_dict(),
            "curation": self.curation.to_dict(),
        }


def _result(name: str, issues: Sequence[Mapping[str, Any]]) -> ValidationResult:
    issue_list = [dict(issue) for issue in issues]
    return ValidationResult(
        name=name,
        passed=not issue_list,
        message=f"{name} is valid." if not issue_list else f"{name} failed validation.",
        details={"issues": issue_list},
    )


def _extend_child_issues(issues: list[dict[str, Any]], validation: ValidationResult) -> None:
    if validation.passed:
        return
    child_issues = validation.details.get("issues", [])
    if isinstance(child_issues, list):
        issues.extend(dict(issue) for issue in child_issues if isinstance(issue, Mapping))


def _require_text(issues: list[dict[str, Any]], field: str, value: Any) -> None:
    if value is None or not str(value).strip():
        issues.append({"field": field, "message": "Required text field is missing."})


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise KineticRecordError(f"Kinetic record field {field!r} must be a mapping.")
    return value


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text.strip() else None


__all__ = [
    "KINETIC_RECORD_KIND",
    "KineticConditions",
    "KineticCuration",
    "KineticEnzyme",
    "KineticLaw",
    "KineticParameter",
    "KineticReaction",
    "KineticRecord",
    "KineticRecordError",
    "KineticReference",
]
