from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from fungal_model.validation.bio_readiness import (
    REQUIRED_BIO_MECHANISM_FIELDS,
    BioReadinessValidationError,
    enforce_bio_mechanism_proposal,
    validate_bio_mechanism_proposal,
    validate_bio_mechanism_proposal_file,
)


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = ROOT / "foundation_progress" / "templates" / "BIO_MECHANISM_PROPOSAL_TEMPLATE.yml"
SCRIPT_PATH = ROOT / "scripts" / "validate_bio_readiness_lite.py"


def test_bio_mechanism_proposal_template_is_machine_checkable() -> None:
    data = yaml.safe_load(TEMPLATE_PATH.read_text(encoding="utf-8"))

    assert isinstance(data, dict)
    assert set(REQUIRED_BIO_MECHANISM_FIELDS).issubset(data)
    assert data["proposal_kind"] == "bio_mechanism_proposal"
    assert str(data["milestone_id"]).startswith("BIO-")
    assert str(data["demo_case"]["case_id"]).startswith("CASE-")
    assert validate_bio_mechanism_proposal(data, proposal_path=TEMPLATE_PATH, allow_template=True).passed


def test_valid_reusable_bio_mechanism_proposal_passes() -> None:
    proposal = _valid_proposal()

    report = validate_bio_mechanism_proposal(proposal)

    assert report.passed
    assert report.issues == ()


def test_incomplete_bio_proposal_is_rejected() -> None:
    proposal = _valid_proposal()
    proposal.pop("parameters")

    report = validate_bio_mechanism_proposal(proposal)

    assert not report.passed
    assert _issue_fields(report) == {"parameters"}
    with pytest.raises(BioReadinessValidationError, match="parameters"):
        enforce_bio_mechanism_proposal(proposal)


def test_bio_case_data_distinction_is_enforced() -> None:
    case_as_bio = {**_valid_proposal(), "milestone_id": "CASE-001"}
    bad_demo = {**_valid_proposal(), "demo_case": {"case_id": "BIO-002"}}
    bad_data_dependency = {**_valid_proposal(), "data_dependencies": ["CASE-001"]}
    stray_case_id = {**_valid_proposal(), "tests_required": ["Re-run CASE-001 before promotion."]}
    stray_data_id = {**_valid_proposal(), "unknowns": ["Estimate from DATA-001 later."]}

    assert _has_issue(validate_bio_mechanism_proposal(case_as_bio), "milestone_id")
    assert _has_issue(validate_bio_mechanism_proposal(bad_demo), "demo_case.case_id")
    assert _has_issue(validate_bio_mechanism_proposal(bad_data_dependency), "data_dependencies")
    assert _has_issue(validate_bio_mechanism_proposal(stray_case_id), "tests_required[0]")
    assert _has_issue(validate_bio_mechanism_proposal(stray_data_id), "unknowns[0]")


def test_organism_specific_bio_proposals_are_rejected() -> None:
    organism_id = {**_valid_proposal(), "mechanism_id": "pleurotus_cellulose_degradation"}
    organism_scope = {
        **_valid_proposal(),
        "valid_enzyme_or_source_classes": ["Pleurotus ostreatus cellulase source"],
    }

    id_report = validate_bio_mechanism_proposal(organism_id)
    scope_report = validate_bio_mechanism_proposal(organism_scope)

    assert _has_issue(id_report, "mechanism_id")
    assert "pleurotus" in id_report.issues[0].message
    assert _has_issue(scope_report, "valid_enzyme_or_source_classes")


def test_cli_validates_proposal_files(tmp_path: Path) -> None:
    valid_path = _write_yaml(tmp_path / "valid.yml", _valid_proposal())
    invalid_path = _write_yaml(
        tmp_path / "invalid.yml",
        {**_valid_proposal(), "mechanism_id": "oryza_sativa_beta_glucosidase_case"},
    )

    valid = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), str(valid_path), "--json"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    invalid = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), str(invalid_path), "--json"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert valid.returncode == 0
    assert json.loads(valid.stdout)[0]["passed"] is True
    assert invalid.returncode == 1
    assert json.loads(invalid.stdout)[0]["passed"] is False


def test_validator_loads_proposal_file(tmp_path: Path) -> None:
    path = _write_yaml(tmp_path / "proposal.yml", _valid_proposal())

    report = validate_bio_mechanism_proposal_file(path)

    assert report.passed
    assert report.proposal_path == str(path)


def _valid_proposal() -> dict[str, Any]:
    return {
        "proposal_kind": "bio_mechanism_proposal",
        "milestone_id": "BIO-TEST",
        "mechanism_id": "generic_substrate_conversion",
        "general_process_family": "generic extracellular substrate conversion",
        "mathematical_law": "dP/dt = yield * r(S, E); dS/dt = -r(S, E)",
        "state_variables": [
            {"name": "substrate_pool", "role": "substrate", "units": "mole / liter"},
            {"name": "product_pool", "role": "product", "units": "mole / liter"},
        ],
        "parameters": [
            {"symbol": "k_process", "meaning": "process rate coefficient", "units": "1 / second"},
        ],
        "units": {
            "state_units_policy": "explicit",
            "parameter_units_policy": "explicit",
        },
        "valid_substrate_classes": ["generic_polymer_fragment"],
        "valid_enzyme_or_source_classes": ["generic_extracellular_catalyst"],
        "environment_variables": [{"name": "temperature", "required": False, "units": "kelvin"}],
        "output_curves": ["substrate_pool", "product_pool"],
        "summary_metrics": ["final_substrate_pool", "final_product_pool"],
        "assumptions": ["Reusable process law independent of one organism or one experiment."],
        "not_in_scope": ["Organism-specific physiology.", "Dataset curation."],
        "unknowns": ["Parameter values require separate DATA-* or curated registry records."],
        "suggested_experiments": ["Measure substrate and product time courses for a CASE-* demo."],
        "blocking_failure_modes": ["Missing state units.", "Missing parameter units."],
        "tests_required": ["Rate-law unit test.", "CASE-* configured workflow smoke test."],
        "limitations": ["Not validated until linked to DATA-* evidence."],
        "demo_case": {
            "case_id": "CASE-TEST",
            "purpose": "Demonstrate the reusable BIO mechanism on one explicit setup.",
        },
        "data_dependencies": ["DATA-TEST"],
        "validation_status": "proposed",
    }


def _issue_fields(report: Any) -> set[str]:
    return {issue.field for issue in report.issues}


def _has_issue(report: Any, field: str) -> bool:
    return field in _issue_fields(report)


def _write_yaml(path: Path, data: dict[str, Any]) -> Path:
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path
