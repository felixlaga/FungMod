from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
FINDINGS_PATH = ROOT / "findings.yaml"

VALID_ORIGINAL_SEVERITIES = {"critical", "high", "medium", "low"}
VALID_CURRENT_SEVERITIES = {"critical", "high", "medium", "low", "informational", "none"}
VALID_STATUSES = {"confirmed", "partially_resolved", "resolved", "stale", "needs_manual_verification"}


def _catalogue() -> dict[str, Any]:
    data = yaml.safe_load(FINDINGS_PATH.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def test_findings_yaml_parses_and_has_findings() -> None:
    data = _catalogue()

    assert data["reviewed_commit_sha"]
    assert data["verified_at"]
    assert isinstance(data["findings"], list)
    assert data["findings"]


def test_finding_ids_are_unique() -> None:
    findings = _catalogue()["findings"]
    ids = [finding["id"] for finding in findings]

    assert len(ids) == len(set(ids))


def test_critical_and_high_original_findings_have_valid_current_status() -> None:
    findings = _catalogue()["findings"]
    reviewed = [
        finding
        for finding in findings
        if finding["original_severity"] in {"critical", "high"}
    ]

    assert reviewed
    for finding in reviewed:
        assert finding["current_status"] in VALID_STATUSES
        assert finding["current_severity"] in VALID_CURRENT_SEVERITIES
        assert finding["original_claim"]


def test_required_evidence_and_verification_sections_exist() -> None:
    for finding in _catalogue()["findings"]:
        assert finding["original_severity"] in VALID_ORIGINAL_SEVERITIES
        assert finding["current_severity"] in VALID_CURRENT_SEVERITIES
        assert finding["current_status"] in VALID_STATUSES
        assert finding["current_assessment"]
        assert finding["technical_status"]
        assert finding["scientific_status"]
        assert finding["remaining_risk"]
        assert finding["recommended_next_action"]

        evidence = finding["evidence"]
        assert set(evidence) == {"code", "tests", "documentation"}
        assert any(evidence[section] for section in evidence)
        for section_entries in evidence.values():
            for entry in section_entries:
                assert entry["path"]
                assert entry["explanation"]

        verification = finding["verification"]
        assert verification["commit_sha"]
        assert verification["verified_at"]
        assert verification["commands_run"]


def test_resolved_and_stale_findings_preserve_original_claims() -> None:
    for finding in _catalogue()["findings"]:
        if finding["current_status"] in {"resolved", "stale"}:
            assert finding["original_claim"]
            assert finding["current_assessment"]


def test_needs_manual_verification_findings_specify_missing_evidence() -> None:
    for finding in _catalogue()["findings"]:
        if finding["current_status"] == "needs_manual_verification":
            missing_text = " ".join(
                [
                    finding["current_assessment"],
                    finding["remaining_risk"],
                    finding["recommended_next_action"],
                ]
            ).lower()
            assert "missing" in missing_text or "manual" in missing_text
