from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
PHASE_1_PLAN = ROOT / "FUNGMOD_PHASE_1_REPOSITORY_TRUTH_AND_EXECUTION_HARDENING.md"
FINDINGS = ROOT / "findings.yaml"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _findings() -> dict[str, Any]:
    data = yaml.safe_load(_read(FINDINGS))
    assert isinstance(data, dict)
    return data


def _normalized(text: str) -> str:
    return " ".join(text.split())


def test_readme_classifies_current_capability_maturity() -> None:
    readme = _read(README)
    normalized = _normalized(readme)

    for label in (
        "implemented",
        "technically verified",
        "exploratory",
        "scientifically validated",
        "unsupported",
    ):
        assert f"`{label}`" in readme

    assert "publication-grade validation" in readme
    assert "BIO-001/BIO-002" in readme
    assert "not a validated default cellulose-degradation model" in normalized


def test_process_adapter_migration_note_matches_current_api_boundary() -> None:
    readme = _read(README)
    normalized = _normalized(readme)

    assert "Former `process.as_reaction()` users" in readme
    assert "AssembledModel.run()" in readme
    assert "run_configured_model" in readme
    assert "construct a low-level" in readme
    assert "Concrete `Process` classes no longer provide" in normalized


def test_legacy_adapter_audit_status_is_current() -> None:
    findings = _findings()
    legacy = next(
        finding
        for finding in findings["findings"]
        if finding["id"] == "P1-AUDIT-LEGACY-REACTION-001"
    )

    assert legacy["current_status"] == "resolved"
    assert legacy["current_severity"] == "none"
    assert "P1.4 removed concrete process-to-Reaction adapters" in legacy["current_assessment"]
    assert "intentionally supported explicit low-level APIs" in legacy["current_assessment"]


def test_active_phase1_docs_do_not_describe_removed_adapters_as_active() -> None:
    active_docs = [
        README,
        ROOT / "ARCHITECTURE_DEBT.md",
        FINDINGS,
        ROOT / "foundation_progress" / "validation" / "PHASE_1_CURRENT_FINDING_STATUS.md",
        ROOT / "foundation_progress" / "validation" / "PHASE_1_NATIVE_EXECUTION_PATHS.md",
        ROOT / "foundation_progress" / "validation" / "PHASE_1_LEGACY_ADAPTER_RETIREMENT.md",
    ]
    forbidden = (
        "Process.as_reaction adapters still exist",
        "compatibility adapters remain",
        "still wraps older non-workflow adapters",
    )

    for path in active_docs:
        text = _read(path)
        for phrase in forbidden:
            assert phrase not in text, path


def test_no_notebook_checkpoints_remain_in_working_tree() -> None:
    checkpoints = sorted((ROOT / "notebooks").glob("**/.ipynb_checkpoints/*"))

    assert checkpoints == []


def test_phase1_plan_is_marked_complete_only_with_checked_gate() -> None:
    plan = _read(PHASE_1_PLAN)

    assert "**Status:** Complete" in plan
    assert "- [ ]" not in plan
    for required in (
        "`AGENTS.md` exists",
        "`findings.yaml` parses",
        "All supported configured well-mixed workflows use native process execution",
        "Legacy adapters are removed",
        "README, progress, roadmap, and architecture debt agree",
        "Ruff passes",
        "Pyright passes",
        "The full test suite passes",
        "Coverage remains at or above the repository gate",
    ):
        assert required in plan
