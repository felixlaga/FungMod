from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATUS_DOC = ROOT / "foundation_progress" / "ROADMAP_ORCHESTRATION_STATUS.md"
README = ROOT / "README.md"
NEXT_STEPS = ROOT / "foundation_progress" / "00_README_NEXT_STEPS_V2.md"
ACTIVE_ROADMAP = ROOT / "foundation_progress" / "FUNGMOD_NEXT_PHASES_ROADMAP.md"
VALIDATION_GATE = ROOT / "foundation_progress" / "VALIDATION_DATA_001_FIRST_TIMECOURSE.md"
PROGRESS_LEDGER = ROOT / "progress.md"
BIO003_DOC = ROOT / "foundation_progress" / "BIO_003_GENERIC_PROCESS_LAWS.md"
BIO003_PROPOSAL = ROOT / "foundation_progress" / "proposals" / "BIO_003_REVERSIBLE_PRODUCT_INHIBITION.yml"
BIO003_COMPETITIVE_PROPOSAL = (
    ROOT / "foundation_progress" / "proposals" / "BIO_003_COMPETITIVE_INHIBITION.yml"
)
BIO003_SUBSTRATE_PROPOSAL = (
    ROOT / "foundation_progress" / "proposals" / "BIO_003_SUBSTRATE_INHIBITION.yml"
)
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
        "ASSEMBLY-001 case-template assembly": "complete for arbitrary reactions using implemented homogeneous Michaelis-Menten semantics and for template-backed surface plus linear/branching/cyclic pathway scopes after PR-56",
        "API-003 researcher-facing virtual experiment API": "complete for existing registry records, aliases, environment grids, scientific/exploratory modes, and table access",
        "BIO-READINESS-LITE scaffold": "complete for proposal template, validator, and tests",
        "BIO-002 reusable extracellular enzyme pathway": "complete for linear, branching, and cyclic graph assembly plus software verification; partial relative to broad pathway biology",
        "Phase 2 static balance checks": "complete for scoped static metadata, validator, assembly-time balance checks, corrective process-reaction binding, and explicit dynamic constraint binding",
    }

    for phase, status in required_statuses.items():
        assert phase in text
        assert status in text

    for boundary in (
        "No fuzzy matching or automatic external fetch",
        "Scientific mode means exact non-exploratory inputs, not empirical validation",
        "No whole-fungus growth, secretion, uptake, biomass, PET, lignin",
        "Explicit configured dynamic constraints now require a passing process-bound electron/redox check",
        "does not infer chemistry, support nonideal activities/reverse fluxes, or validate biology",
    ):
        assert boundary in text


def test_pr48_parameter_authoring_contract_is_synchronized() -> None:
    readme = _read(README)
    status = _read(STATUS_DOC)
    next_steps = _read(NEXT_STEPS)
    roadmap = _read(ACTIVE_ROADMAP)
    validation_gate = _read(VALIDATION_GATE)
    progress = _read(PROGRESS_LEDGER)

    for text in (readme, status, next_steps, roadmap, progress):
        assert "plan_registry_promotion" in text
        assert "apply_registry_promotion" in text

    for text in (status, next_steps, roadmap, validation_gate, progress):
        assert "PR-46" in text
        assert "PR #61" in text
        assert "2b6c639" in text
        assert "PR-47" in text
        assert "PR #62" in text
        assert "b1ebb860" in text
        assert "PR-48" in text

    for text in (readme, status, next_steps, roadmap, progress):
        assert "author_parameter_record" in text
        assert "identity" in text.lower()
        assert "PARAMETER" in text

    for phrase in (
        "plan schema `2.0.0`",
        "exact plan digest",
        "exact next numeric patch version",
        "full-root",
        "same-filesystem registry copy",
        "verified rollback",
        "At that historical PR-47 checkpoint product maps",
    ):
        assert phrase in next_steps

    assert "`product_maps/product_maps.yml` destination" in readme
    assert "parameter_records" in readme
    assert "strict numeric `MAJOR.MINOR.PATCH`" in readme
    assert "Pre-PR-47 written schema `1.0.0`" in readme
    assert "`plan_digest`/`confirmation_digest`" in progress
    assert "simulation_authorized: false" in progress
    assert "structural non-downgrade" in status
    assert "complete independent apply revalidation" in status
    assert "ordinary curator/date/role metadata" in status
    assert "Checksums prove internal consistency, not curator authorship" in status
    assert "`Km` role to runtime key `km`" in progress
    for text in (readme, status, next_steps, roadmap, progress):
        assert "load_curation_bundle" in text
        assert "internal" in text and "consistency" in text
    assert "LoadedCurationBundle" in readme
    assert "exact inventory" in status
    assert "no registry mutation" in roadmap.lower()
    for text in (readme, status, next_steps, roadmap, progress):
        assert "source-to-production" in text
        assert "nonidentity" in text.lower()
        assert "non-parameter" in text.lower()
        assert "Ed25519" in text
    assert "CURATION-001 is complete for" in readme
    assert "AuthenticatedCurationBundle" in readme
    assert "Trust is explicit and caller-owned" in readme


def test_active_docs_identify_current_next_pr_and_do_not_bind_old_progress() -> None:
    status = _read(STATUS_DOC)
    next_steps = _read(NEXT_STEPS)
    roadmap = _read(ACTIVE_ROADMAP)

    current_next = "none selected; scoped queue complete through PR-59"
    assert f"Current next PR: **{current_next}**" in status
    assert f"Current next PR: **{current_next}**" in next_steps
    assert (
        "No next PR\nis selected; the user-scoped queue is complete through PR-59"
        in roadmap
    )
    assert "The PR-31 slice should bridge" not in roadmap
    assert "PR-31 is deliberately build-first" not in roadmap
    assert "The completed PR-31 slice bridged explicit" in roadmap
    assert "The completed PR-33 slice extends the explicit registry-template environment" in roadmap
    assert "The completed PR-34 slice is limited to configured-output conservation/drift" in roadmap
    assert "The completed PR-35 slice is limited to\nrepository hygiene guardrails" in roadmap
    assert "The completed PR-36\nslice is limited to configured-output solver diagnostics" in roadmap
    assert "The completed PR-37\nslice is limited to Markdown, HTML, and report-folder index visibility" in roadmap
    assert "completed PR-38 slice is limited to a package-output-driven solver diagnostics" in roadmap
    assert "completed PR-39 slice is limited\nto a standard virtual-experiment `solver_diagnostics.csv`" in roadmap
    assert "completed\nPR-40 slice is limited to a standard virtual-experiment" in roadmap
    assert "`conservation_diagnostics.csv` table/accessor bridge" in roadmap
    assert "completed PR-41 slice enabled Pyright `reportOptionalMemberAccess`" in roadmap
    assert "completed PR-42 slice generalized the registry/template-driven extracellular" in roadmap
    assert "completed PR-43 slice adds post-simulation" in roadmap
    assert "completed PR-44" in roadmap
    assert "completed PR-45" in roadmap
    assert "completed PR-46" in roadmap
    assert "completed PR-47" in roadmap
    assert "completed PR-48" in roadmap
    assert "completed PR-49" in roadmap
    assert "completed PR-50" in roadmap
    assert "completed PR-51" in roadmap
    assert "completed PR-52" in roadmap
    assert "PR-53" in roadmap
    assert "PR-54" in roadmap
    assert "PR-55" in roadmap
    assert "PR-56" in roadmap
    assert "PR-57" in roadmap
    assert "PR-58" in roadmap
    assert "branching, cycles, disconnected chains, and malformed topology" in roadmap
    assert "35 baseline nullable-member errors across 11" in roadmap
    assert "scientific modules using explicit contracts" in roadmap
    assert "PR-30\nconfigured oxygen/water-activity modifier example notebook slice" in roadmap
    assert "PR-29\nexplicit oxygen/water-activity configured modifier wiring slice" in roadmap
    assert "PR-28\nconfigured environment modifier example notebook slice" in roadmap
    assert "PR-27\nexplicit configured environmental rate-modifier wiring slice" in roadmap
    assert "PR-25 THERMO-003 virtual-experiment\nthermodynamic diagnostics bridge" in roadmap
    assert "PR-24 BIO-003 non-PET product-inhibition\ngenericity-hardening slice" in roadmap
    assert "PR-23 PRODUCT-001 provenance/limitations report\nexample notebook" in roadmap
    assert "PR-22 PRODUCT-001 provenance/limitations report" in roadmap
    assert "PR-21 THERMO-003 explicit thermodynamic-summary report" in roadmap
    assert "PR-20 threshold-time inspection/report ergonomics" in roadmap
    assert "PR-19 degradation-rate quicklook/report\nergonomics" in roadmap
    assert "PR-18 trajectory-quantile example and\nquicklook ergonomics" in roadmap
    assert "PR-17 trajectory-quantile\noutput ergonomics" in roadmap
    assert "PR-16\nuncertainty-band output ergonomics" in roadmap
    assert "PR-15 entropy-budget output notebook inspection" in roadmap
    assert "PR-14 THERMO-003 configured entropy-budget summary" in roadmap
    assert "PR-13 THERMO-003 entropy-production-rate notebook" in roadmap
    assert "PR-12 comparison/report-output" in roadmap
    assert "PR-11 screen-comparison summary ergonomics" in roadmap
    assert "PR-10 report-folder index/navigation" in roadmap

    for text in (status, next_steps):
        assert "old_progress/" in text
        assert "historical" in text
        assert "non-binding" in text

    assert "ROADMAP_ORCHESTRATION_STATUS.md" in next_steps
    assert "ROADMAP_ORCHESTRATION_STATUS.md" in roadmap


def test_build_first_queue_defers_validation_without_deleting_it() -> None:
    readme = _read(README)
    status = _read(STATUS_DOC)
    next_steps = _read(NEXT_STEPS)
    roadmap = _read(ACTIVE_ROADMAP)

    current_next = "none selected; scoped queue complete through PR-59"
    for text in (status, next_steps):
        assert f"Current next PR: **{current_next}**" in text
        assert "Current next PR: **PR-03" not in text
        assert "Current next PR: **PR-04" not in text
        assert "Current next PR: **PR-08" not in text
        assert "Current next PR: **PR-07" not in text
        assert "Current next PR: **PR-09" not in text
        assert "Current next PR: **PR-10" not in text
        assert "Current next PR: **PR-11" not in text
        assert "Current next PR: **PR-12" not in text
        assert "Current next PR: **PR-13" not in text
        assert "Current next PR: **PR-14" not in text
        assert "Current next PR: **PR-15" not in text
        assert "Current next PR: **PR-16" not in text
        assert "Current next PR: **PR-17" not in text
        assert "Current next PR: **PR-18" not in text
        assert "Current next PR: **PR-19" not in text
        assert "Current next PR: **PR-20" not in text
        assert "Current next PR: **PR-21" not in text
        assert "Current next PR: **PR-22" not in text
        assert "Current next PR: **PR-23" not in text
        assert "Current next PR: **PR-24" not in text
        assert "Current next PR: **PR-25" not in text
        assert "Current next PR: **PR-26" not in text
        assert "Current next PR: **PR-27" not in text
        assert "Current next PR: **PR-28" not in text
        assert "Current next PR: **PR-29" not in text
        assert "Current next PR: **PR-30" not in text
        assert "Current next PR: **PR-31" not in text
        assert "Current next PR: **PR-32" not in text
        assert "Current next PR: **PR-33" not in text
        assert "Current next PR: **PR-34" not in text
        assert "Current next PR: **PR-35" not in text
        assert "Current next PR: **PR-36" not in text
        assert "Current next PR: **PR-37" not in text
        assert "Current next PR: **PR-38" not in text
        assert "Current next PR: **PR-39" not in text
        assert "Current next PR: **PR-40" not in text
        assert "Current next PR: **PR-41" not in text
        assert "Current next PR: **PR-42" not in text
        assert "Current next PR: **PR-43" not in text
        assert "Current next PR: **PR-44" not in text
        assert "Current next PR: **PR-45" not in text
        assert "Current next PR: **PR-46" not in text
        assert "Current next PR: **PR-47" not in text
        assert "Current next PR: **PR-48" not in text
        assert "Current next PR: **PR-49" not in text
        assert "Current next PR: **PR-50" not in text
        assert "Current next PR: **PR-51" not in text
        assert "Current next PR: **PR-52" not in text
        assert "Current next PR: **PR-53" not in text
        assert "Current next PR: **PR-54" not in text
        assert "Current next PR: **PR-55" not in text
        assert "Current next PR: **PR-56" not in text
        assert "Current next PR: **PR-57" not in text
        assert "Current next PR: **PR-58" not in text
        assert "Current next PR: **PR-59" not in text

    for phase in ("PRODUCT-001", "THERMO-003", "BIO-003", "VALIDATION-DATA-001"):
        assert phase in status
        assert phase in next_steps
        assert phase in roadmap

    assert "mechanism_summary.csv" in status
    assert "mechanism_summary.csv" in next_steps
    assert "comparison_summary.csv" in status
    assert "comparison_summary.csv" in next_steps
    assert "DegradationScreenResult.comparison_summary()" in next_steps
    assert "uncertainty_summary.csv" in status
    assert "uncertainty_summary.csv" in next_steps
    assert "DegradationScreenResult.uncertainty_summary()" in next_steps
    assert "trajectory_quantiles.csv" in status
    assert "trajectory_quantiles.csv" in next_steps
    assert "DegradationScreenResult.trajectory_quantiles()" in next_steps
    assert "thermodynamic_diagnostics.csv" in status
    assert "thermodynamic_diagnostics.csv" in next_steps
    assert "DegradationScreenResult.thermodynamic_diagnostics()" in next_steps
    assert "conservation_diagnostics.csv" in status
    assert "conservation_diagnostics.csv" in next_steps
    assert "conservation_diagnostics.json" in next_steps
    assert "DegradationScreenResult.conservation_diagnostics()" in next_steps
    assert "inferred conserved quantities" in next_steps
    assert "solver_diagnostics.csv" in status
    assert "solver_diagnostics.csv" in next_steps
    assert "DegradationScreenResult.solver_diagnostics()" in next_steps
    assert "solver_diagnostics.json" in next_steps
    assert "solver_diagnostics.csv" in readme
    assert "Standard virtual-experiment outputs now also include `solver_diagnostics.csv`" in next_steps
    assert "solver_diagnostics.csv` copies existing per-sample configured-output" in status
    assert "solver quality thresholds" in next_steps
    assert "19_solver_diagnostics_example.ipynb" in status
    assert "19_solver_diagnostics_example.ipynb" in next_steps
    assert "19_solver_diagnostics_example.ipynb" in readme
    assert "package-generated solver diagnostics artifact inspection" in status
    assert "header-only/no-metadata" in next_steps
    assert "existing configured run metadata" in status
    assert "Report utilities now expose existing configured-output `solver_diagnostics.json`" in next_steps
    assert "Added Markdown, HTML, and report-folder index visibility for existing configured-output" in status
    assert "header-only CSV plus JSON\n`status: unavailable` behavior" in next_steps
    assert "existing `SimulationResult` state trajectories" in status
    assert "Header-only\nCSV and `evaluated_count: 0` JSON behavior" in next_steps
    assert "trajectory_quantile_bands.png" in status
    assert "degradation_rate_vs_time.png" in status
    assert "degradation_rate_vs_time.png" in next_steps
    assert "time_series_long.csv" in status
    assert "bounded degradation-rate inspection section" in next_steps
    assert "threshold_times.csv" in status
    assert "summary_metrics.csv" in status
    assert "summary_metrics.csv" in next_steps
    assert "simulated threshold summaries" in status
    assert "14_trajectory_quantiles_example.ipynb" in status
    assert "14_trajectory_quantiles_example.ipynb" in next_steps
    assert "ranking_blocking_reason" in status
    assert "13_screen_comparison_summary_example.ipynb" in status
    assert "13_screen_comparison_summary_example.ipynb" in next_steps
    assert "15_provenance_limitations_report_example.ipynb" in status
    assert "15_provenance_limitations_report_example.ipynb" in next_steps
    assert "16_thermodynamic_diagnostics_example.ipynb" in status
    assert "16_thermodynamic_diagnostics_example.ipynb" in next_steps
    assert "17_configured_environment_modifiers_example.ipynb" in status
    assert "17_configured_environment_modifiers_example.ipynb" in next_steps
    assert "17_configured_environment_modifiers_example.ipynb" in readme
    assert "18_configured_oxygen_water_modifiers_example.ipynb" in status
    assert "18_configured_oxygen_water_modifiers_example.ipynb" in next_steps
    assert "18_configured_oxygen_water_modifiers_example.ipynb" in readme
    assert "DegradationScreenResult.write_report(...)" in next_steps
    assert "include_html=True" in next_steps
    assert "include_index=True" in next_steps
    assert "write_report(...)" in status
    assert "include_html=True" in status
    assert "include_index=True" in status
    assert "10_virtual_experiment_product_tour.ipynb" in status
    assert "10_virtual_experiment_product_tour.ipynb" in next_steps
    assert "11_thermodynamics_entropy_diagnostics.ipynb" in status
    assert "11_thermodynamics_entropy_diagnostics.ipynb" in next_steps
    assert "12_reversible_product_inhibition_example.ipynb" in status
    assert "12_reversible_product_inhibition_example.ipynb" in next_steps
    assert "toy_surface_dummy_non_pet_product_inhibition.yml" in status
    assert "toy_surface_dummy_non_pet_product_inhibition.yml" in next_steps
    assert "toy_surface_dummy_non_pet_product_inhibition.yml" in readme
    assert "All four load through `load_model_config`" in readme
    assert "All three load through `load_model_config`" not in readme
    assert "temperature_arrhenius_reference" in status
    assert "ph_gaussian" in status
    assert "oxygen_monod" in status
    assert "water_activity_threshold" in status
    assert "temperature_arrhenius_reference" in next_steps
    assert "ph_gaussian" in next_steps
    assert "oxygen_monod" in next_steps
    assert "water_activity_threshold" in next_steps
    assert "temperature_arrhenius_reference" in readme
    assert "ph_gaussian" in readme
    assert "oxygen_monod" in readme
    assert "water_activity_threshold" in readme
    assert "thermodynamic_summary.json" in status
    assert "thermodynamic_summary.csv" in status
    assert "header-only when no artifacts exist" in status
    assert "report utilities now expose existing configured-output thermodynamic summary and solver diagnostics artifacts" in status
    assert "thermodynamic_summary.csv` artifacts without inferring thermodynamic inputs" in next_steps
    assert "When PR-57 dynamic rows are present" in next_steps
    assert "provenance/limitation decision summary" in status
    assert "decision-support table links" in next_steps
    assert "provenance/limitations report example-notebook slice" in next_steps
    assert "VALIDATION-DATA-001 now has one evidence-gated" in next_steps
    assert "has_entropy_production_rate" in next_steps
    assert "has_entropy_budget" in next_steps
    assert "entropy_budget_negative_count" in next_steps
    assert "entropy_budget_status" in next_steps
    assert "configured entropy-budget summary" in status
    assert "entropy-budget output notebook inspection" in status
    assert "uncertainty-band output ergonomics" in status
    assert "entropy-production-rate, and entropy-budget output inspection" in next_steps
    assert "Validation remains important" in status
    assert "first same-source no-calibration comparison complete" in status
    assert "coupled substrate transglycosylation" in next_steps
    assert "BIO_003_SUBSTRATE_TRANSGLYCOSYLATION.yml" in next_steps
    assert "four bounded mechanism targets" in status
    assert "phanerochaete_bgl1b_cellobiose_transglycosylation.yml" in status
    assert "Validation data is important, but it should not block PRODUCT-001" in _read(
        ROOT / "foundation_progress" / "FUNGMOD_NEXT_PHASES_ROADMAP_V2.md"
    )
    assert "VALIDATION-DATA-001: complete for the bounded first same-source" in next_steps
    assert "PR-08 | PRODUCT-001 virtual-experiment report writer" in status
    assert "PR-09 | PRODUCT-001 HTML report wrapper" in status
    assert "PR-10 | PRODUCT-001 report-folder index/navigation" in status
    assert "PR-11 | PRODUCT-001 screen-comparison summary ergonomics" in status
    assert "PR-12 | PRODUCT-001 comparison/report-output example notebook" in status
    assert "PR-13 | THERMO-003 entropy-production-rate notebook coverage" in status
    assert "PR-14 | THERMO-003 configured entropy-budget summary" in status
    assert "PR-15 | THERMO-003 entropy-budget output notebook inspection" in status
    assert "PR-16 | PRODUCT-001 uncertainty-band output ergonomics" in status
    assert "PR-17 | PRODUCT-001 trajectory-quantile output ergonomics" in status
    assert "PR-18 | PRODUCT-001 trajectory-quantile example and quicklook ergonomics" in status
    assert "PR-19 | PRODUCT-001 degradation-rate quicklook/report ergonomics" in status
    assert "PR-20 | PRODUCT-001 threshold-time inspection/report ergonomics" in status
    assert "PR-21 | THERMO-003 explicit thermodynamic-summary report ergonomics" in status
    assert "PR-22 | PRODUCT-001 provenance/limitations report ergonomics" in status
    assert "PR-23 | PRODUCT-001 provenance/limitations report example notebook" in status
    assert "PR-24 | BIO-003 non-PET product-inhibition genericity hardening" in status
    assert "complete after PR #39 merged for the scoped build-first genericity-hardening slice" in status
    assert "PR-25 | THERMO-003 virtual-experiment thermodynamic diagnostics bridge" in status
    assert "complete after PR #40 merged for the scoped standard-table/accessor bridge" in status
    assert "PR-26 | THERMO-003 virtual-experiment thermodynamic diagnostics example notebook" in status
    assert "complete after PR #41 merged for the scoped public-API example-notebook slice" in status
    assert "PR-27 | Explicit configured environmental rate modifiers" in status
    assert "complete after PR #42 merged for the scoped configured modifier wiring slice" in status
    assert "PR-28 | Configured environment modifier example notebook" in status
    assert "complete after PR #43 merged for the scoped public configured-workflow example notebook slice" in status
    assert "PR-29 | Explicit oxygen and water-activity configured modifiers" in status
    assert "complete after PR #44 merged for the scoped configured modifier wiring slice" in status
    assert "PR-30 | Configured oxygen and water-activity modifier example notebook" in status
    assert "complete after PR #45 merged for the scoped public configured-workflow example notebook slice" in status
    assert "PR-31 | Registry-backed explicit environment modifier assembly" in status
    assert "complete after PR #46 merged for the scoped one-process registry template modifier bridge" in status
    assert "PR-32 | Repository hygiene cleanup" in status
    assert "complete after PR #47 merged for the scoped repository hygiene slice" in status
    assert "PR-33 | Chain-template explicit environment modifier assembly" in status
    assert "complete after PR #48 merged for the scoped chain-template environment modifier bridge" in status
    assert "PR-34 | Configured-output conservation/drift diagnostics" in status
    assert "complete after PR #49 merged for the scoped configured-output conservation/drift diagnostics slice" in status
    assert "PR-35 | Focused repository hygiene guardrail extension" in status
    assert "complete after PR #50 merged for the scoped repository hygiene guardrail extension" in status
    assert "PR-36 | Configured-output solver diagnostics" in status
    assert "complete after PR #51 merged for the scoped configured-output solver diagnostics slice" in status
    assert "PR-37 | Solver diagnostics visibility follow-up" in status
    assert "complete after PR #52 merged for the scoped report/index visibility slice" in status
    assert "PR-38 | Solver diagnostics example notebook" in status
    assert "complete after PR #53 merged for the scoped public configured-workflow example notebook slice" in status
    assert "PR-39 | Virtual-experiment solver diagnostics bridge" in status
    assert "complete after PR #54 merged for the scoped standard-table/accessor bridge" in status
    assert "PR-40 | Virtual-experiment conservation diagnostics bridge" in status
    assert "complete after PR #55 merged for the scoped standard-table/accessor bridge" in status
    assert "PR-41 | Pyright optional-member-access ratchet" in status
    assert "complete after PR #56 merged for the scoped typing-quality ratchet" in status
    assert "35 baseline nullable-member errors across 11 scientific modules" in status
    assert "PR-42 | Arbitrary-length linear enzyme-chain assembly" in status
    assert "complete after PR #57 merged for the bounded linear-topology slice" in status
    assert "PR-43 | THERMO-003 process-bound entropy-production-rate timeseries" in status
    assert "complete after PR #58 merged for the bounded configured-output diagnostics slice" in status
    assert "PR-44 | Researcher source-provider onboarding UX" in status
    assert "complete after PR #59 merged" in status
    assert "PR-45 | CURATION-001 source-proposal review and decision bundle" in status
    assert "complete after PR #60 merged as `5ac7864`" in status
    assert "PR-46 | CURATION-001 registry-promotion preview plan" in status
    assert "PR-47 | CURATION-001 digest-confirmed transactional apply" in status
    assert "complete after PR #61 merged as `2b6c639`" in status
    assert "complete after PR #62 merged as `b1ebb860`; CURATION-001 remains partial" in status
    assert (
        "PR-48 | CURATION-001 identity-only curator-authored ParameterRecord bridge"
    ) in status
    assert "complete after PR #63 merged as `764d1e4`; CURATION-001 remains partial" in status
    assert "PR-49 | CURATION-001 reusable public curation-bundle loader" in status
    assert "complete after PR #64 merged as `bbe2ee6`" in status
    assert "PR-50 | CURATION-001 checksum-loaded written source input" in status
    assert "complete after PR #65 merged as `933d2c8`" in status
    assert "PR-51 | CURATION-001 versioned nonidentity ParameterRecord conversion registry" in status
    assert "complete after PR #66 merged as `bef938f` for the bounded registered-conversion scope" in status
    assert "PR-52 | CURATION-001 non-parameter curator-authored registry-record bridge" in status
    assert "complete after PR #67 merged as `5da611b` for the five index-backed" in status
    assert "PR-53 | CURATION-001 product-map registry destination and ownership contract" in status
    assert "PR-54 | CURATION-001 authenticated curator-signature contract" in status
    assert "complete after PR #68 merged as `19baedd` | Added an empty index-owned production destination" in status
    assert "completes CURATION-001 for its defined curation workflow" in status
    assert "PR-55 | Arbitrary reaction onboarding and assembly contract" in status
    assert "complete after PR #70 merged as `6b3d275` | Removed Reaction 618/SABIO-RK" in status
    assert "PR-56 | Branching and cyclic enzyme-pathway assembly contract" in status
    assert (
        "complete after PR #71 merged as `caa0a17` | Added explicit "
        "`linear`/`branching`/`cyclic`"
    ) in status
    assert "PR-57 | Dynamic thermodynamic feasibility and solver-enforcement contract" in status
    assert "complete after PR #72 merged as `ae8a5a3` | Added optional explicit ideal-dilute" in status
    assert "PR-58 | Broader provenance-backed biological laws contract" in status
    assert "complete after PR #73 merged as `68c715b` | Added provenance-bound competitive" in status
    assert "PR-59 | Final PRODUCT-001 integration" in status
    assert "complete in the current checkout | Added schema `1.8.0`" in status
    assert "PR-57 | Dynamic thermodynamic feasibility and solver-enforcement contract" in status
    assert "caller-supplied trust" in status
    assert "exact manifest authorship" in status
    assert "exact storage-only policy blocks simulation in every mode" in status
    assert "closed exact per-mode `allowed_use` permissions" in status
    assert "intrinsic component-only scope" in status
    assert "load/query-validated registry authority graph" in status
    assert "exact initial/modifier semantic role keys" in status
    assert "initial-state roles declare record scope rather than kinetic ownership" in status
    assert "entropy_production_rate_timeseries.json" in next_steps
    assert "entropy_production_rate_timeseries.json" in _read(README)
    assert "no silent conversion" in status
    assert "The branch/cycle cases are artificial software fixtures" in status
    assert "Current | VALIDATION-DATA-001" in status


def test_active_docs_select_bio003_product_inhibition_without_overclaiming() -> None:
    status = _read(STATUS_DOC)
    next_steps = _read(NEXT_STEPS)
    progress = _read(PROGRESS_LEDGER)
    bio003_doc = _read(BIO003_DOC)
    proposal = _read(BIO003_PROPOSAL)

    for text in (status, next_steps, progress, bio003_doc, proposal):
        assert "reversible product inhibition" in text

    assert "partial/software-tested for configured and registry-backed reversible product inhibition" in status
    assert "partial/software-tested for generic reversible product inhibition" in next_steps
    assert "ProductInhibitionModifier" in bio003_doc
    assert "toy_surface_dummy_non_pet_product_inhibition.yml" in bio003_doc
    assert "non-PET toy surface benchmark" in bio003_doc
    assert "validation_status: software_tested" in proposal
    assert "Configured model processes can now opt into it" in next_steps
    assert "registry-backed case assembly" in progress
    assert "complete for the scoped" in progress
    assert "researcher-facing example gap on the selected reversible-product-inhibition" in progress
    assert "researcher-facing example for this reversible-product-inhibition target" in next_steps
    assert "covered by `notebooks/examples/12_reversible_product_inhibition_example.ipynb`" in next_steps
    assert "No organism-specific inhibition behavior" in progress


def test_pr58_biological_laws_are_provenance_bound_and_do_not_overclaim() -> None:
    readme = _read(README)
    status = _read(STATUS_DOC)
    next_steps = _read(NEXT_STEPS)
    roadmap = _read(ACTIVE_ROADMAP)
    progress = _read(PROGRESS_LEDGER)
    bio003_doc = _read(BIO003_DOC)
    competitive = _read(BIO003_COMPETITIVE_PROPOSAL)
    substrate = _read(BIO003_SUBSTRATE_PROPOSAL)

    for text in (readme, status, next_steps, roadmap, progress, bio003_doc):
        assert "competitive" in text.lower()
        assert "Haldane" in text
        assert "homogeneous Michaelis-Menten" in text
    for proposal in (competitive, substrate):
        assert "proposal_kind: bio_mechanism_proposal" in proposal
        assert "validation_status: software_tested" in proposal
        assert "primary_provenance:" in proposal
        assert "No empirical validation" in proposal
    assert "https://pubmed.ncbi.nlm.nih.gov/7985803/" in competitive
    assert "https://doi.org/10.1016/j.biortech.2010.01.084" in substrate
    assert "artificial software benchmarks" in readme
    assert "not production applicability or validation" in next_steps
    assert "whole-fungus" in progress


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


def test_validation_data_gate_tracks_ingestion_complete_and_comparison_pending() -> None:
    status = _read(STATUS_DOC)
    next_steps = _read(NEXT_STEPS)
    gate = _read(VALIDATION_GATE)
    roadmap = _read(ACTIVE_ROADMAP)

    current_next = "none selected; scoped queue complete through PR-59"
    for text in (status, next_steps):
        assert current_next in text
        assert "PR-03" not in _current_next_lines(text)
        assert "PR-04" not in _current_next_lines(text)
        assert "PR-05" not in _current_next_lines(text)
        assert "PR-08" not in _current_next_lines(text)
        assert "PR-07" not in _current_next_lines(text)
        assert "PR-09" not in _current_next_lines(text)
        assert "PR-10" not in _current_next_lines(text)
        assert "PR-11" not in _current_next_lines(text)
        assert "PR-12" not in _current_next_lines(text)
        assert "PR-13" not in _current_next_lines(text)
        assert "PR-14" not in _current_next_lines(text)
        assert "PR-15" not in _current_next_lines(text)
        assert "PR-16" not in _current_next_lines(text)
        assert "PR-17" not in _current_next_lines(text)
        assert "PR-18" not in _current_next_lines(text)
        assert "PR-19" not in _current_next_lines(text)
        assert "PR-20" not in _current_next_lines(text)
        assert "PR-21" not in _current_next_lines(text)
        assert "PR-22" not in _current_next_lines(text)
        assert "PR-23" not in _current_next_lines(text)
        assert "PR-24" not in _current_next_lines(text)
        assert "PR-25" not in _current_next_lines(text)
        assert "PR-26" not in _current_next_lines(text)
        assert "PR-27" not in _current_next_lines(text)
        assert "PR-28" not in _current_next_lines(text)
        assert "PR-29" not in _current_next_lines(text)
        assert "PR-30" not in _current_next_lines(text)
        assert "PR-31" not in _current_next_lines(text)
        assert "PR-32" not in _current_next_lines(text)
        assert "PR-33" not in _current_next_lines(text)
        assert "PR-34" not in _current_next_lines(text)
        assert "PR-35" not in _current_next_lines(text)
        assert "PR-36" not in _current_next_lines(text)
        assert "PR-37" not in _current_next_lines(text)
        assert "PR-38" not in _current_next_lines(text)
        assert "PR-39" not in _current_next_lines(text)
        assert "PR-40" not in _current_next_lines(text)
        assert "PR-41" not in _current_next_lines(text)
        assert "PR-42" not in _current_next_lines(text)
        assert "PR-43" not in _current_next_lines(text)
        assert "PR-44" not in _current_next_lines(text)
        assert "PR-45" not in _current_next_lines(text)
        assert "PR-46" not in _current_next_lines(text)
        assert "PR-47" not in _current_next_lines(text)
        assert "PR-48" not in _current_next_lines(text)
        assert "PR-49" not in _current_next_lines(text)
        assert "PR-50" not in _current_next_lines(text)
        assert "PR-51" not in _current_next_lines(text)
        assert "PR-52" not in _current_next_lines(text)
        assert "PR-53" not in _current_next_lines(text)
        assert "PR-54" not in _current_next_lines(text)
        assert "PR-55" not in _current_next_lines(text)
        assert "PR-56" not in _current_next_lines(text)
        assert "PR-57" not in _current_next_lines(text)
        assert "PR-58" not in _current_next_lines(text)

    assert "Current next task: acquire an independent or held-out" in gate

    assert "VALIDATION-DATA-001 independent validation evidence | first same-source" in status
    assert "VALIDATION-DATA-001: complete for the bounded first same-source" in next_steps
    assert "Status: `complete` for the bounded first same-source" in gate
    assert "PR-36 configured-output solver diagnostics is complete after PR #51" in gate
    assert "PR-37 solver diagnostics visibility follow-up is complete after PR #52" in gate
    assert "PR-38\nsolver diagnostics example notebook is complete after PR #53" in gate
    assert "PR-39\nvirtual-experiment solver diagnostics bridge is complete after PR #54" in gate
    assert "PR-40\nvirtual-experiment conservation diagnostics bridge is complete after PR #55" in gate
    assert "PR-41 Pyright optional-member-access ratchet is complete after PR #56" in gate
    assert "arbitrary-length linear enzyme-chain assembly is complete after PR #57" in gate
    assert "process-bound entropy-production-rate diagnostics is complete after PR #58" in gate
    assert "PR-44 researcher source-provider onboarding is complete after PR #59" in gate
    assert "PR-45 CURATION-001 proposal-review and decision-bundle work is complete" in gate
    assert "PR-46 registry-promotion planning is complete" in gate
    assert "PR-48 identity-only PARAMETER authoring is complete" in gate
    assert "PR-50 checksum-loaded\nwritten-source authoring is complete" in gate
    assert "PR-51 scope is complete after PR #66 merged as `bef938f`" in gate
    assert "PR-52 follow-up is complete after PR #67 merged as `5da611b`" in gate
    assert "PR-53 is complete after PR #68\nmerged as `19baedd` with product-map production ownership" in gate
    assert "PR-54 is complete after PR #69 merged as\n`35a3ecb` with" in gate
    assert "PR-55 is complete after PR #70 merged as `6b3d275` with arbitrary reaction onboarding" in gate
    assert "intentional plan\nschema `2.0.0`" in gate
    assert "CURATION-001 is complete for\nits defined review" in gate
    assert "PR-49 reusable public checksum-validated" in gate
    assert "Future validation-data additions must not ingest" in gate
    assert "unless the same evidence requirements are met" in gate
    assert "not independent validation" in gate
    assert "first dataset's separately implemented comparison slice" in gate
    assert "VALIDATION-DATA-001" in gate
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
        "model_comparison.csv",
        "residuals.csv",
        "validation_report.md",
    ):
        assert excluded_artifact in gate


def _current_next_lines(text: str) -> str:
    return "\n".join(line for line in text.splitlines() if "Current next PR:" in line)
