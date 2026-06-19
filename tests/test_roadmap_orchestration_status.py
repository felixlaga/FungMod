from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATUS_DOC = ROOT / "foundation_progress" / "ROADMAP_ORCHESTRATION_STATUS.md"
NEXT_STEPS = ROOT / "foundation_progress" / "00_README_NEXT_STEPS_V2.md"
ACTIVE_ROADMAP = ROOT / "foundation_progress" / "FUNGMOD_NEXT_PHASES_ROADMAP.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_roadmap_orchestration_status_document_exists_with_workflow_contract() -> None:
    text = _read(STATUS_DOC)

    for phrase in (
        "Maker thread works in its own worktree and branch",
        "Reviewer thread reviews the PR",
        "comment loop",
        "merge the PR",
        "The next maker starts from this tracker",
        "Every PR summary and task report must state",
        "Do not call live external APIs from tests or simulation",
        "Do not add silent fallback constants",
        "Do not treat proposed source records as production registry records",
    ):
        assert phrase in text


def test_status_tracker_reconciles_completed_scoped_slices_without_overclaiming() -> None:
    text = _read(STATUS_DOC)

    required_statuses = {
        "SOURCE-002 notebook-driven SABIO-RK discovery and proposals": "complete for scoped offline discovery/proposal workflow",
        "RESOLVE-001 name and alias resolver": "complete for strict registry-backed exact and case-insensitive alias resolution",
        "ASSEMBLY-001 case-template assembly basics": "complete for current Reaction 618 and BIO-001 template-backed assembly basics; partial relative to arbitrary reaction onboarding",
        "API-003 researcher-facing virtual experiment API": "complete for existing registry records, aliases, environment grids, scientific/exploratory modes, and table access",
        "BIO-READINESS-LITE scaffold": "complete for proposal template, validator, and tests",
        "BIO-002 reusable two-step extracellular enzyme chain": "complete for scoped reusable two-step chain assembly and software verification; partial relative to broad pathway biology",
        "Phase 2 static balance checks": "complete for scoped static metadata, validator, assembly-time balance checks, and corrective process-reaction binding; partial relative to dynamic thermodynamic feasibility",
    }

    for phase, status in required_statuses.items():
        assert phase in text
        assert status in text

    for boundary in (
        "No fuzzy matching or automatic external fetch",
        "Scientific mode means exact non-exploratory inputs, not empirical validation",
        "No whole-fungus growth, secretion, uptake, biomass, PET, lignin",
        "No dynamic reaction quotients, activity model, redox potential model",
    ):
        assert boundary in text


def test_active_docs_identify_current_next_pr_and_do_not_bind_old_progress() -> None:
    status = _read(STATUS_DOC)
    next_steps = _read(NEXT_STEPS)
    roadmap = _read(ACTIVE_ROADMAP)

    current_next = "PR-03: VALIDATION-DATA-001 first real time-course dataset and model comparison"
    assert f"Current next PR: **{current_next}**" in status
    assert f"Current next PR: **{current_next}**" in next_steps
    assert "The current next PR is VALIDATION-DATA-001 after PR-02" in roadmap

    for text in (status, next_steps):
        assert "old_progress/" in text
        assert "historical" in text
        assert "non-binding" in text

    assert "ROADMAP_ORCHESTRATION_STATUS.md" in next_steps
    assert "ROADMAP_ORCHESTRATION_STATUS.md" in roadmap


def test_pr03_validation_data_status_is_blocked_without_advancing_queue() -> None:
    status = _read(STATUS_DOC)
    next_steps = _read(NEXT_STEPS)
    validation_doc = _read(ROOT / "foundation_progress" / "VALIDATION_DATA_001_FIRST_TIMECOURSE.md")

    current_next = "PR-03: VALIDATION-DATA-001 first real time-course dataset and model comparison"
    assert f"Current next PR: **{current_next}**" in status
    assert f"Current next PR: **{current_next}**" in next_steps
    assert "blocked pending ingestable source" in status
    assert "blocked pending an ingestable public source" in next_steps
    assert "Status: `blocked pending ingestable source`" in validation_doc
    assert "must not resolve that conflict by inference or majority" in validation_doc
    assert "VALIDATION-DATA-001 is not complete" in validation_doc
    assert "PR-04" in status
    assert "Current next PR: **PR-04" not in status
    assert "Current next PR: **PR-04" not in next_steps
