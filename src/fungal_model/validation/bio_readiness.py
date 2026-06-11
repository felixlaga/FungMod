"""BIO-READINESS-LITE proposal validation."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


ID_PATTERN = re.compile(r"\b(BIO|CASE|DATA)-[A-Za-z0-9][A-Za-z0-9_-]*\b")

REQUIRED_BIO_MECHANISM_FIELDS = (
    "proposal_kind",
    "milestone_id",
    "mechanism_id",
    "general_process_family",
    "mathematical_law",
    "state_variables",
    "parameters",
    "units",
    "valid_substrate_classes",
    "valid_enzyme_or_source_classes",
    "environment_variables",
    "output_curves",
    "summary_metrics",
    "assumptions",
    "not_in_scope",
    "unknowns",
    "suggested_experiments",
    "blocking_failure_modes",
    "tests_required",
    "limitations",
    "demo_case",
    "validation_status",
)

VALIDATION_STATUS_VALUES = frozenset(
    {
        "proposed",
        "software_tested",
        "source_supported",
        "calibrated",
        "validated",
    }
)

ORGANISM_SPECIFIC_TOKENS = frozenset(
    {
        "aspergillus",
        "bacteroides",
        "candida",
        "hordeum",
        "oryza",
        "phanerochaete",
        "pleurotus",
        "thermotoga",
        "albicans",
        "chrysosporium",
        "niger",
        "ostreatus",
        "sativa",
    }
)


@dataclass(frozen=True)
class BioReadinessIssue:
    """One machine-checkable BIO-READINESS-LITE issue."""

    field: str
    message: str
    severity: str = "error"

    def to_dict(self) -> dict[str, str]:
        return {
            "field": self.field,
            "message": self.message,
            "severity": self.severity,
        }


@dataclass(frozen=True)
class BioReadinessReport:
    """Result of BIO-READINESS-LITE validation."""

    proposal_path: str
    passed: bool
    issues: tuple[BioReadinessIssue, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal_path": self.proposal_path,
            "passed": self.passed,
            "issues": [issue.to_dict() for issue in self.issues],
        }


class BioReadinessValidationError(ValueError):
    """Raised when BIO-READINESS-LITE enforcement fails."""


def load_bio_mechanism_proposal(path: str | Path) -> dict[str, Any]:
    """Load a BIO mechanism proposal YAML mapping."""

    proposal_path = Path(path)
    data = yaml.safe_load(proposal_path.read_text(encoding="utf-8"))
    if not isinstance(data, Mapping):
        raise BioReadinessValidationError(f"BIO proposal must be a YAML mapping: {proposal_path}")
    return dict(data)


def validate_bio_mechanism_proposal(
    proposal: Mapping[str, Any],
    *,
    proposal_path: str | Path = "<memory>",
    allow_template: bool = False,
) -> BioReadinessReport:
    """Validate a BIO proposal as a reusable mechanism rather than a case/data artifact."""

    issues: list[BioReadinessIssue] = []
    issues.extend(_required_field_issues(proposal, allow_template=allow_template))
    if not issues or allow_template:
        issues.extend(_bio_case_data_distinction_issues(proposal))
        issues.extend(_mechanism_generality_issues(proposal))
        issues.extend(_structured_field_issues(proposal))
    error_issues = tuple(issue for issue in issues if issue.severity == "error")
    return BioReadinessReport(
        proposal_path=str(proposal_path),
        passed=not error_issues,
        issues=tuple(issues),
    )


def validate_bio_mechanism_proposal_file(
    path: str | Path,
    *,
    allow_template: bool = False,
) -> BioReadinessReport:
    """Load and validate one BIO mechanism proposal file."""

    return validate_bio_mechanism_proposal(
        load_bio_mechanism_proposal(path),
        proposal_path=path,
        allow_template=allow_template,
    )


def enforce_bio_mechanism_proposal(
    proposal: Mapping[str, Any],
    *,
    proposal_path: str | Path = "<memory>",
    allow_template: bool = False,
) -> BioReadinessReport:
    """Validate a proposal and raise if it does not pass."""

    report = validate_bio_mechanism_proposal(
        proposal,
        proposal_path=proposal_path,
        allow_template=allow_template,
    )
    if not report.passed:
        messages = "; ".join(f"{issue.field}: {issue.message}" for issue in report.issues)
        raise BioReadinessValidationError(messages)
    return report


def _required_field_issues(
    proposal: Mapping[str, Any],
    *,
    allow_template: bool,
) -> tuple[BioReadinessIssue, ...]:
    issues: list[BioReadinessIssue] = []
    for field_name in REQUIRED_BIO_MECHANISM_FIELDS:
        if field_name not in proposal:
            issues.append(BioReadinessIssue(field_name, "Required BIO mechanism proposal field is missing."))
            continue
        if not allow_template and _is_empty(proposal[field_name]):
            issues.append(BioReadinessIssue(field_name, "Required BIO mechanism proposal field is empty."))
    return tuple(issues)


def _bio_case_data_distinction_issues(proposal: Mapping[str, Any]) -> tuple[BioReadinessIssue, ...]:
    issues: list[BioReadinessIssue] = []
    proposal_kind = str(proposal.get("proposal_kind", ""))
    milestone_id = str(proposal.get("milestone_id", ""))
    mechanism_id = str(proposal.get("mechanism_id", ""))
    if proposal_kind != "bio_mechanism_proposal":
        issues.append(BioReadinessIssue("proposal_kind", "BIO proposals must use proposal_kind='bio_mechanism_proposal'."))
    if not milestone_id.startswith("BIO-"):
        issues.append(BioReadinessIssue("milestone_id", "BIO mechanism proposals must use a BIO-* milestone_id."))
    issues.extend(_id_placement_issues(proposal))
    for field_name, value in (("mechanism_id", mechanism_id), ("general_process_family", proposal.get("general_process_family", ""))):
        text = str(value)
        if text.startswith(("CASE-", "DATA-")) or "case_" in text.lower() or "data_" in text.lower():
            issues.append(BioReadinessIssue(field_name, "BIO mechanism identity must not be a CASE-* or DATA-* artifact."))
    demo_case = proposal.get("demo_case", {})
    if isinstance(demo_case, Mapping):
        case_id = str(demo_case.get("case_id", ""))
        if not case_id.startswith("CASE-"):
            issues.append(BioReadinessIssue("demo_case.case_id", "demo_case.case_id must identify a CASE-* demonstration."))
    else:
        issues.append(BioReadinessIssue("demo_case", "demo_case must be a mapping with a CASE-* case_id."))
    for dependency in _sequence(proposal.get("data_dependencies", ())):
        if not str(dependency).startswith("DATA-"):
            issues.append(BioReadinessIssue("data_dependencies", "data_dependencies entries must be DATA-* IDs."))
    return tuple(issues)


def _id_placement_issues(proposal: Mapping[str, Any]) -> tuple[BioReadinessIssue, ...]:
    issues: list[BioReadinessIssue] = []
    for field_path, text in _scalar_text_items(proposal):
        for match in ID_PATTERN.finditer(text):
            id_kind = match.group(1)
            if id_kind == "BIO" and field_path != "milestone_id":
                issues.append(BioReadinessIssue(field_path, "BIO-* IDs are only allowed in milestone_id."))
            elif id_kind == "CASE" and not field_path.startswith("demo_case."):
                issues.append(BioReadinessIssue(field_path, "CASE-* IDs are only allowed in demo_case."))
            elif id_kind == "DATA" and not field_path.startswith("data_dependencies["):
                issues.append(BioReadinessIssue(field_path, "DATA-* IDs are only allowed in data_dependencies."))
    return tuple(issues)


def _mechanism_generality_issues(proposal: Mapping[str, Any]) -> tuple[BioReadinessIssue, ...]:
    issues: list[BioReadinessIssue] = []
    for field_name in (
        "mechanism_id",
        "general_process_family",
        "valid_substrate_classes",
        "valid_enzyme_or_source_classes",
        "assumptions",
        "limitations",
    ):
        organism_tokens = _organism_tokens(proposal.get(field_name))
        if organism_tokens:
            issues.append(
                BioReadinessIssue(
                    field_name,
                    "BIO mechanism proposals must be reusable process mechanisms, not organism-specific cases. "
                    f"Organism-specific token(s): {', '.join(sorted(organism_tokens))}.",
                )
            )
    mechanism_id = str(proposal.get("mechanism_id", ""))
    if not mechanism_id or not re.fullmatch(r"[a-z][a-z0-9_]*", mechanism_id):
        issues.append(
            BioReadinessIssue(
                "mechanism_id",
                "mechanism_id must be a stable lowercase mechanism identifier, e.g. extracellular_enzyme_chain.",
            )
        )
    return tuple(issues)


def _structured_field_issues(proposal: Mapping[str, Any]) -> tuple[BioReadinessIssue, ...]:
    issues: list[BioReadinessIssue] = []
    for field_name in (
        "state_variables",
        "parameters",
        "valid_substrate_classes",
        "valid_enzyme_or_source_classes",
        "environment_variables",
        "output_curves",
        "summary_metrics",
        "assumptions",
        "not_in_scope",
        "unknowns",
        "suggested_experiments",
        "blocking_failure_modes",
        "tests_required",
        "limitations",
    ):
        if not _is_nonempty_sequence(proposal.get(field_name)):
            issues.append(BioReadinessIssue(field_name, "Field must be a non-empty list."))
    for index, state in enumerate(_sequence(proposal.get("state_variables"))):
        if not isinstance(state, Mapping):
            issues.append(BioReadinessIssue(f"state_variables[{index}]", "State variable entries must be mappings."))
            continue
        for key in ("name", "role", "units"):
            if _is_empty(state.get(key)):
                issues.append(BioReadinessIssue(f"state_variables[{index}].{key}", "State variable field is required."))
    for index, parameter in enumerate(_sequence(proposal.get("parameters"))):
        if not isinstance(parameter, Mapping):
            issues.append(BioReadinessIssue(f"parameters[{index}]", "Parameter entries must be mappings."))
            continue
        for key in ("symbol", "meaning", "units"):
            if _is_empty(parameter.get(key)):
                issues.append(BioReadinessIssue(f"parameters[{index}].{key}", "Parameter field is required."))
    status = str(proposal.get("validation_status", ""))
    if status not in VALIDATION_STATUS_VALUES:
        allowed = ", ".join(sorted(VALIDATION_STATUS_VALUES))
        issues.append(BioReadinessIssue("validation_status", f"validation_status must be one of: {allowed}."))
    return tuple(issues)


def _organism_tokens(value: Any) -> set[str]:
    tokens = set(re.findall(r"[a-z]+", _flatten_text(value).lower()))
    return tokens & ORGANISM_SPECIFIC_TOKENS


def _flatten_text(value: Any) -> str:
    if isinstance(value, Mapping):
        return " ".join(_flatten_text(item) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return " ".join(_flatten_text(item) for item in value)
    return "" if value is None else str(value)


def _scalar_text_items(value: Any, path: str = "") -> tuple[tuple[str, str], ...]:
    if isinstance(value, Mapping):
        items: list[tuple[str, str]] = []
        for key, item in value.items():
            item_path = f"{path}.{key}" if path else str(key)
            items.extend(_scalar_text_items(item, item_path))
        return tuple(items)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        items = []
        for index, item in enumerate(value):
            item_path = f"{path}[{index}]"
            items.extend(_scalar_text_items(item, item_path))
        return tuple(items)
    return ((path, "" if value is None else str(value)),)


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        stripped = value.strip()
        return not stripped or stripped.startswith("<") and stripped.endswith(">")
    if isinstance(value, Mapping):
        return not value
    if isinstance(value, Sequence):
        return not value
    return False


def _is_nonempty_sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes)) and bool(value)


def _sequence(value: Any) -> tuple[Any, ...]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return tuple(value)
    return ()


__all__ = [
    "BioReadinessIssue",
    "BioReadinessReport",
    "BioReadinessValidationError",
    "REQUIRED_BIO_MECHANISM_FIELDS",
    "VALIDATION_STATUS_VALUES",
    "enforce_bio_mechanism_proposal",
    "load_bio_mechanism_proposal",
    "validate_bio_mechanism_proposal",
    "validate_bio_mechanism_proposal_file",
]
