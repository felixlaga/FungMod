from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATUS_DOC = ROOT / "foundation_progress" / "ROADMAP_ORCHESTRATION_STATUS.md"
NEXT_STEPS = ROOT / "foundation_progress" / "00_README_NEXT_STEPS_V2.md"
ACTIVE_ROADMAP = ROOT / "foundation_progress" / "FUNGMOD_NEXT_PHASES_ROADMAP.md"
VALIDATION_GATE = ROOT / "foundation_progress" / "VALIDATION_DATA_001_FIRST_TIMECOURSE.md"
PROGRESS_LEDGER = ROOT / "progress.md"
BIO003_DOC = ROOT / "foundation_progress" / "BIO_003_GENERIC_PROCESS_LAWS.md"
BIO003_PROPOSAL = ROOT / "foundation_progress" / "proposals" / "BIO_003_REVERSIBLE_PRODUCT_INHIBITION.yml"
FINAL_GOAL_PLAN = ROOT / "foundation_progress" / "FUNGMOD_FINAL_GOAL_PR_PLAN_2026_06_20.html"


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
        "Explicit caller-supplied reaction-quotient Gibbs checks now exist",
        "no inferred activity model, redox potential model, or solver-time thermodynamic enforcement",
    ):
        assert boundary in text


def test_active_docs_identify_current_next_pr_and_do_not_bind_old_progress() -> None:
    status = _read(STATUS_DOC)
    next_steps = _read(NEXT_STEPS)
    roadmap = _read(ACTIVE_ROADMAP)

    current_next = "PR-05: PRODUCT-001 build-first exploratory virtual-experiment expansion"
    assert f"Current next PR: **{current_next}**" in status
    assert f"Current next PR: **{current_next}**" in next_steps
    assert "The current next PR is PRODUCT-001" in roadmap

    for text in (status, next_steps):
        assert "old_progress/" in text
        assert "historical" in text
        assert "non-binding" in text

    assert "ROADMAP_ORCHESTRATION_STATUS.md" in next_steps
    assert "ROADMAP_ORCHESTRATION_STATUS.md" in roadmap


def test_build_first_queue_defers_validation_without_deleting_it() -> None:
    status = _read(STATUS_DOC)
    next_steps = _read(NEXT_STEPS)
    roadmap = _read(ACTIVE_ROADMAP)

    current_next = "PR-05: PRODUCT-001 build-first exploratory virtual-experiment expansion"
    for text in (status, next_steps):
        assert f"Current next PR: **{current_next}**" in text
        assert "Current next PR: **PR-03" not in text
        assert "Current next PR: **PR-04" not in text

    for phase in ("PRODUCT-001", "THERMO-003", "BIO-003", "VALIDATION-DATA-001"):
        assert phase in status
        assert phase in next_steps
        assert phase in roadmap

    assert "mechanism_summary.csv" in status
    assert "mechanism_summary.csv" in next_steps
    assert "Validation remains important" in status
    assert "Real observations are required for validation/calibration/comparison claims" in status
    assert "Validation data is important, but it should not block PRODUCT-001" in _read(
        ROOT / "foundation_progress" / "FUNGMOD_NEXT_PHASES_ROADMAP_V2.md"
    )
    assert "VALIDATION-DATA-001: deferred; blocked/partial" in next_steps
    assert "PR-08 | VALIDATION-DATA-001" in status


def test_active_docs_select_bio003_product_inhibition_without_overclaiming() -> None:
    status = _read(STATUS_DOC)
    next_steps = _read(NEXT_STEPS)
    progress = _read(PROGRESS_LEDGER)
    bio003_doc = _read(BIO003_DOC)
    proposal = _read(BIO003_PROPOSAL)

    for text in (status, next_steps, progress, bio003_doc, proposal):
        assert "reversible product inhibition" in text

    assert "partial/software-tested for configured reversible product inhibition" in status
    assert "partial/software-tested for generic reversible product inhibition" in next_steps
    assert "ProductInhibitionModifier" in bio003_doc
    assert "validation_status: software_tested" in proposal
    assert "Configured model processes can now opt into it" in next_steps
    assert "registry-backed case assembly remains future work" in proposal
    assert "No organism-specific inhibition behavior" in progress


def test_final_goal_html_plan_records_pr_slices_and_notebook_candidates() -> None:
    html = _read(FINAL_GOAL_PLAN)

    for phrase in (
        "PR-14 recommendation",
        "BIO-003 proposal selection",
        "Notebook Plan",
        "BIO-003 mechanism notebook",
        "VALIDATION-DATA-001 should start only when",
    ):
        assert phrase in html


def test_validation_data_gate_keeps_pr03_current_and_not_complete() -> None:
    status = _read(STATUS_DOC)
    next_steps = _read(NEXT_STEPS)
    gate = _read(VALIDATION_GATE)
    roadmap = _read(ACTIVE_ROADMAP)

    current_next = "PR-05: PRODUCT-001 build-first exploratory virtual-experiment expansion"
    for text in (status, next_steps, gate):
        assert current_next in text
        assert "PR-03" not in _current_next_lines(text)
        assert "PR-04" not in _current_next_lines(text)

    assert "VALIDATION-DATA-001 first real time-course dataset | deferred; blocked/partial" in status
    assert "VALIDATION-DATA-001: deferred; blocked/partial for ingestion" in next_steps
    assert "Status: `deferred; blocked/partial` for ingestion." in gate
    assert "Status: `complete`" not in gate
    assert "does not complete VALIDATION-DATA-001" in gate
    assert "validation, calibration, or empirical comparison claims" in roadmap
    assert "it should not block PRODUCT-001" in _read(
        ROOT / "foundation_progress" / "FUNGMOD_NEXT_PHASES_ROADMAP_V2.md"
    )


def test_validation_data_gate_records_required_evidence_and_blockers() -> None:
    gate = _read(VALIDATION_GATE)

    for required_field in (
        "figure_or_table_or_supplement_identifier",
        "observation_rows",
        "units",
        "extraction_or_transcription_method",
        "extractor_and_date",
        "preprocessing_and_conversion_notes",
        "uncertainty_policy",
        "explicit_limitations",
    ):
        assert required_field in gate

    for blocked_candidate_fact in (
        "resa_buckin_2011_cellobiose_hydrolysis_review.yml",
        "blocked_do_not_ingest",
        "ariaeenejad_2020_persibgl1_cellobiose_hydrolysis_review.yml",
        "blocked_time_axis_conflict_do_not_ingest",
        "method used 24-h intervals until",
        "Figure 6 caption says 380 h",
        "one nearby result sentence says conversion reaches zero after 380 min",
        "Choosing hours by majority evidence would be an inference",
    ):
        assert blocked_candidate_fact in gate

    for excluded_artifact in (
        "raw_data.csv",
        "curated_data.csv",
        "model_comparison.csv",
        "residuals.csv",
        "validation_report.md",
    ):
        assert excluded_artifact in gate


def _current_next_lines(text: str) -> str:
    return "\n".join(line for line in text.splitlines() if "Current next PR:" in line)
