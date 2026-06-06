from __future__ import annotations

import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
FOUNDATION_GATE_CANDIDATES = (
    ROOT / "FOUNDATION_COMPLETE.md",
    ROOT / "past_progress" / "FOUNDATION_COMPLETE.md",
    ROOT / "old_progress" / "FOUNDATION_COMPLETE.md",
)


def _section(text: str, heading: str) -> str:
    pattern = rf"^## {re.escape(heading)}\n(?P<body>.*?)(?=^## |\Z)"
    match = re.search(pattern, text, flags=re.MULTILINE | re.DOTALL)
    assert match is not None, f"Missing FOUNDATION_COMPLETE.md section: {heading}"
    return match.group("body")


def _foundation_status(text: str) -> str:
    match = re.search(r"^Status:\s*(?P<status>[^\n]+)$", text, flags=re.MULTILINE)
    assert match is not None
    return match.group("status").strip().lower()


def _active_debt_ids(debt_register: str) -> set[str]:
    active_ids: set[str] = set()
    for match in re.finditer(
        r"^## (?P<id>FD-\d+)[^\n]*\n(?P<body>.*?)(?=^## |\Z)",
        debt_register,
        flags=re.MULTILINE | re.DOTALL,
    ):
        if re.search(r"^Status:\s*active\s*$", match.group("body"), flags=re.MULTILINE):
            active_ids.add(match.group("id"))
    return active_ids


def _documented_non_blocking_ids(foundation_gate: str) -> set[str]:
    section = _section(foundation_gate, "Active Non-Blocking Architecture Debt")
    return set(re.findall(r"`(FD-\d+)`", section))


def _foundation_gate_path() -> Path:
    for path in FOUNDATION_GATE_CANDIDATES:
        if path.exists():
            return path
    pytest.skip(
        "Historical FOUNDATION_COMPLETE.md archive is absent. "
        "Skipping documentation gate only; code tests remain active."
    )


def test_foundation_complete_gate_exists_and_is_explicit() -> None:
    gate_path = _foundation_gate_path()

    gate = gate_path.read_text(encoding="utf-8")
    status = _foundation_status(gate)

    assert status in {"not complete", "complete"}
    assert "software foundation only" in gate
    assert "does not approve" in gate
    assert "real fungal biology" in gate


def test_complete_foundation_gate_requires_all_evidence() -> None:
    gate = _foundation_gate_path().read_text(encoding="utf-8")
    status = _foundation_status(gate)

    if status != "complete":
        return

    criteria = _section(gate, "Completion Criteria")
    required_checked_items = (
        "all guardrail tests pass",
        "all configured workflow tests pass",
        "all failure-path tests pass",
        "all maturity-mode tests pass",
        "all output reproducibility tests pass",
        "CI passes",
        "coverage gate passes",
        "no active foundation-blocking architecture debt remains",
        "PET is plugin-only",
        "notebooks use public APIs only",
        "README honestly states limitations",
        "`run_configured_model` runs homogeneous, dummy non-PET, and PET-plugin foundation configs",
    )

    for item in required_checked_items:
        assert f"- [x] {item}" in criteria

    evidence = _section(gate, "Required Evidence")
    required_evidence = (
        "tests/test_guardrails_no_hardcoding.py",
        "tests/test_guardrails_no_shortcuts.py",
        "tests/test_guardrails_public_api.py",
        "tests/test_guardrails_config_generality.py",
        "tests/test_guardrails_native_execution.py",
        "tests/test_configured_model_workflow.py",
        "tests/test_configured_workflow_failures.py",
        "tests/test_maturity_policy.py",
        "tests/test_configured_output_bundle_reproducibility.py",
        "tests/test_notebooks.py",
        "tests/test_quality_config.py",
        "tests/test_foundation_complete_gate.py",
    )

    for test_path in required_evidence:
        assert test_path in evidence
        assert (ROOT / test_path).exists()


def test_complete_foundation_gate_blocks_undocumented_active_debt() -> None:
    gate = _foundation_gate_path().read_text(encoding="utf-8")
    status = _foundation_status(gate)

    if status != "complete":
        return

    debt_register = (ROOT / "ARCHITECTURE_DEBT.md").read_text(encoding="utf-8")
    active_ids = _active_debt_ids(debt_register)
    documented_non_blocking_ids = _documented_non_blocking_ids(gate)

    assert active_ids <= documented_non_blocking_ids
    assert "foundation-blocking architecture debt" in gate
    for debt_id in active_ids:
        non_blocking_entry = _section(gate, "Active Non-Blocking Architecture Debt")
        assert debt_id in non_blocking_entry
        assert "not a foundation-blocking architecture debt" in non_blocking_entry
