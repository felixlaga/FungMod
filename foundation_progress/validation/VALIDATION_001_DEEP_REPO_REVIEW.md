# VALIDATION-001 Deep Repository Review

Date: 2026-06-07

Mode: validation/review only. No source code, registry records, data records, or notebooks were changed.

Central directive reviewed: `foundation_progress/FUNGMOD_CENTRAL_GOAL_VIRTUAL_EXPERIMENTS.md`.

Validation spec reviewed: `foundation_progress/VALIDATION_001_DEEP_REPO_REVIEW_SPEC.md`.

## Executive Summary

FungMod has moved meaningfully toward the central goal: it now has a registry-backed `VirtualExperiment` API that performs modelability preflight, runs exploratory simulations, and writes long-format time series, final metrics, thresholds, sampled parameters, summary metrics, provenance, limitations, and quick-look plots. Reaction 618 is still scientifically honest: the selected SABIO-RK exact values are separated from the missing enzyme concentration and from the user-supplied exploratory enzyme prior. ENV-001 correctly treats environment grids as metadata-only unless a response law exists. DATA-002 preserves local SABIO-RK curation and broad ranges with explicit limitations. BIO-001 is a controlled exploratory surface-degradation pilot, not a whole-fungus model.

The repository is not publication-ready as a scientific virtual-experiment engine yet. The most important blockers are output semantics and public API maturity: scientific-mode virtual experiments are not exposed through the public `VirtualExperiment.simulate()` API, BIO-001 reports a mass-valued product as a "concentration", accessible-site fraction is a derived proxy rather than a modeled state, and metadata-only environment grids can still look like comparable environmental response screens if users ignore limitations. Passing tests show that current software contracts execute; they do not validate the biology.

Recommendation: pause new biology and broad new data ingestion. Consolidate the API/output schema, observable semantics, scientific/exploratory gates, and documentation entry points first.

## Files And Areas Reviewed

Reviewed directly or by targeted search:

- `README.md`
- `pyproject.toml`
- `ARCHITECTURE_DEBT.md`
- `progress.md`
- `foundation_progress/FUNGMOD_CENTRAL_GOAL_VIRTUAL_EXPERIMENTS.md`
- `foundation_progress/VALIDATION_001_DEEP_REPO_REVIEW_SPEC.md`
- `foundation_progress/ENV_001_ENVIRONMENT_GRIDS.md`
- `foundation_progress/DATA_002_REACTION_618_PARAMETER_RANGES.md`
- `foundation_progress/BIO_001_CELLULOSE_SURFACE_DEGRADATION.md`
- `src/fungal_model/__init__.py`
- `src/fungal_model/api/`
- `src/fungal_model/screening/`
- `src/fungal_model/data/`
- `src/fungal_model/registry/`
- `src/fungal_model/processes/`
- `src/fungal_model/workflows/`
- `src/fungal_model/calibration/`
- `src/fungal_model/io/`
- `src/fungal_model/validation/`
- `data_registry/`
- `data/`
- `notebooks/`
- `tests/`
- `scripts/`

Folders requested by the validation spec exist: `src/fungal_model/`, `src/fungal_model/api/`, `src/fungal_model/screening/`, `src/fungal_model/data/`, `src/fungal_model/registry/`, `src/fungal_model/processes/`, `src/fungal_model/workflows/`, `src/fungal_model/calibration/`, `data_registry/`, `data/`, `notebooks/`, `tests/`, `foundation_progress/`, and `scripts/`.

## Current Maturity Rating

Overall maturity: 6/10.

This is a credible mechanistic virtual-experiment scaffold with strong guardrails for the first enzyme-only case and a controlled exploratory surface case. It is not yet a stable publication-grade researcher product because the public scientific API, output schema, observable naming, and validation-data story are incomplete.

## Maturity Scores

| Dimension | Score | Explanation |
| --- | ---: | --- |
| Central-goal alignment | 7 | API-001 outputs degradation dynamics, not just modelability; still missing some central recommended tables and exact/scientific public run mode. |
| Architecture foundation | 6 | Modular packages and registries exist; case assembly still has named-case branches and hardcoded state/time defaults. |
| Public researcher API | 5 | `VirtualExperiment.from_registry(...).simulate(...)` exists, but requires registry IDs and only supports exploratory simulation. |
| Low-level developer API | 7 | Model config, process factories, solver, registry, and deterministic builder are usable and tested. |
| Registry/data model | 6 | Good provenance and ValueSpec structure; range interpretation and observable schema need stronger machine-readable semantics. |
| Scientific honesty | 7 | Strong limitations and exploratory labels; product/concentration naming and metadata-only environment comparisons remain risky. |
| Biological realism | 4 | Reaction 618 enzyme kinetics is narrow and honest; BIO-001 is simplified surface catalysis with exploratory priors only. |
| Output-table quality | 7 | Main API-001 tables exist and are tested; some tables are not self-contained and some central recommended outputs are missing. |
| Notebook usability | 6 | Notebooks use public APIs and show tables; custom plotting and path setup are okay but lint policy is unclear. |
| Testing depth | 7 | 450 tests pass, including API, notebooks, DATA/ENV/BIO; tests do not prove empirical validity. |
| Data provenance | 7 | Reaction 618 raw/curated separation and EntryID provenance are good; BIO-001 parameters are clearly exploratory. |
| Extensibility | 6 | Process factories are generic, but case-specific assembly branches will not scale cleanly. |
| Atmodeller-like usability | 4 | The conceptual flow exists for registry IDs, but not yet human-friendly names, scientific mode, or broad screen ergonomics. |
| Overall maturity | 6 | Ready for schema/API hardening; not ready for new biology or public scientific use. |

## Central-Goal Alignment Audit

1. Does the current codebase primarily help simulate degradation dynamics over time?

Yes, for the current scoped cases. `VirtualExperiment.simulate()` writes trajectories and metrics. Modelability is not the final output.

2. Or is it drifting into modelability-only checks, registry decoration, or data dumping?

The recent direction is not modelability-only. The risk is now output-semantics debt rather than lack of simulation.

3. Does the public API hide internal complexity from researchers?

Partially. Researchers can use `VirtualExperiment.from_registry()`, but they must still know registry IDs and only exploratory mode is public.

4. Can a researcher define a virtual experiment and receive degradation outputs?

Yes, from registry IDs and in exploratory mode.

5. Are output tables centered on substrate loss, product release, rates, threshold times, uncertainty, provenance, and limitations?

Mostly yes. The requested API-001 tables exist. Missing or partial central-goal outputs include first-class `missing_parameters.csv`, `suggested_experiments.csv`, and `trajectory_quantiles.csv`.

6. Are modelability checks correctly treated as preflight guardrails?

Mostly yes. `VirtualExperiment.simulate()` runs preflight internally and blocks unsupported/underparameterized cases. However, preflight text saying no ODE is assembled can appear inside simulation limitations and should be clarified.

7. Are notebooks demonstrating the actual degradation process, or mostly internal infrastructure?

The Reaction 618 and BIO-001 notebooks demonstrate public API simulation and output tables. Foundation notebooks still demonstrate configured workflow infrastructure.

8. Are plots optional and derived from tables?

Yes. Quick-look plots are optional and read from `time_series_long.csv`.

9. Are tables publication-friendly?

Partially. They include core context and units, but observable semantics need tightening, especially BIO-001 product concentration and proxy accessibility.

10. Are limitations explicit enough to prevent overclaiming?

Better than average, but not sufficient alone. Scientific safety should not depend on users reading a limitations row after seeing plots and metrics.

## Architecture Assessment

Strengths:

- `src/fungal_model/api/` now provides a clear virtual-experiment layer.
- `src/fungal_model/screening/modelability.py` separates modelability from simulation and preserves known/uncertain/missing/incompatible evidence.
- `src/fungal_model/screening/ensemble.py` samples ValueSpecs and records samples, outputs, failures, and trajectories.
- `src/fungal_model/processes/surface.py` is generic surface catalysis, not a cellulose-only process.
- Registry records separate fungi/source, substrate, enzyme class, environment, process compatibility, and parameters.

Architecture debts:

- `case_builder.py` hardcodes Reaction 618 and BIO-001 state names, product-map naming, and time-grid defaults.
- `result_tables.py` reads generated sample model-config YAML files back from disk to infer state roles. This works but makes the output layer depend on transient generated config structure.
- The public API exposes exploratory simulation only, while exact deterministic scientific assembly exists below.
- `summary_metrics.csv` is keyed by `case_id`, metric, and units; biological context requires joining to `case_summary.csv`.
- Broad per-sample exception capture in ensemble simulation is useful, but run quality is not surfaced strongly enough.

## Public API Assessment

Current public API can support:

```python
study = VirtualExperiment.from_registry(
    fungi=["sabiork_beta_glucosidase_source"],
    substrates=["cellobiose"],
    environments=["sabiork_reaction_618_selected_conditions"],
)
result = study.simulate(mode="exploratory", n_samples=128)
result.write_tables()
result.write_quicklook_plots()
```

What is missing:

- `fungal_model.virtual_experiment(...)` top-level convenience matching the central conceptual API.
- Human-readable names/aliases.
- Public `simulate(mode="scientific")`.
- Public time-grid controls.
- Public control over output table set and schema version.
- First-class missing-parameter/suggested-experiment tables.
- A stable result object named around degradation outputs rather than screen internals.

## Researcher Workflow Assessment

The workflow is now plausible for a developer-researcher comfortable with registry IDs. It is not yet polished for a bench scientist. A user can run Reaction 618 and BIO-001 notebooks and inspect tables. The friction points are registry ID discovery, exploratory-only simulation, and the need to understand limitations deeply.

## Scientific-Model Assessment

Reaction 618:

- Correctly treated as enzyme-source homogeneous Michaelis-Menten on cellobiose.
- Not whole-fungus degradation.
- Scientific preflight remains underparameterized because enzyme concentration is unknown.
- Exploratory run uses a user-supplied enzyme concentration prior, clearly marked.

DATA-002:

- Uses local SABIO-RK snapshot.
- Writes eligible and excluded entries.
- Preserves EntryIDs, pH, temperature, units, publication metadata, and exclusion reasons.
- Broad ranges are properly described as exploratory literature priors, not selected-entry uncertainty.

ENV-001:

- Environment grid creates cases and stable IDs.
- pH/temperature are metadata-only unless response models exist.
- Output tables include environment metadata and limitations.

BIO-001:

- Adds enzyme-mediated insoluble cellulose-like surface degradation through existing generic surface catalysis.
- Does not add whole-fungus growth, secretion, uptake, biomass, oxygen limitation, or lignocellulose decomposition.
- All numerical values are exploratory priors.
- Important flaw: product is named concentration while using amount units.
- Important simplification: accessible-site fraction is a derived proxy from substrate remaining.

## Data And Provenance Assessment

Strengths:

- Raw and curated SABIO-RK files are separated.
- DATA-002 eligible/excluded tables and parameter-range summaries exist.
- Registry parameter records keep selected exact, unknown, literature range, and exploratory prior records distinct.
- BIO-001 exploratory priors use `maturity: exploratory_prior` and `confidence_level: exploratory_assumption`.
- Synthetic/toy data folders are documented as non-empirical.

Concerns:

- Range interpretation is still mostly prose/provenance rather than machine-actionable policy.
- README entry points still refer to moved foundation progress docs.
- `.DS_Store`, `.coverage`, and `coverage.xml` are ignored/local artifacts; not a scientific problem, but validation reports should not depend on them.

## Output-Table Assessment

| Output | Status | Responsible code | Test coverage | Problems |
| --- | --- | --- | --- | --- |
| `modelability_preflight.csv` | exists | `api/result_tables.py` | API/env tests | Good, but preflight wording can confuse simulated results. |
| `case_summary.csv` | exists | `api/result_tables.py` | API tests | Good; should include run-quality severity. |
| `time_series_long.csv` | exists | `api/result_tables.py` | API/BIO tests | Good long format; BIO proxy/product semantics need fixing. |
| `final_states.csv` | exists | `api/result_tables.py` and lower screen output | API tests | Good scalar states. |
| `final_metrics.csv` | exists | `api/result_tables.py` | API/BIO tests | Product concentration naming/unit risk. |
| `threshold_times.csv` | exists | `api/result_tables.py`, `api/metrics.py` | BIO threshold tests | Good; not-reached cases handled. |
| `sampled_parameters.csv` | exists | `api/result_tables.py` | API/DATA/BIO tests | Good source-class fields; range interpretation should be stronger. |
| `sampled_parameter_summary.csv` | partial | lower `screen_result.save()` | ensemble tests | Exists from lower layer, but not integrated into `WrittenTables`. |
| `summary_metrics.csv` | exists | `api/result_tables.py` | API/BIO tests | Needs biological context columns or explicit join schema. |
| `trajectory_quantiles.csv` | missing | none | none | Needed for publication-ready uncertainty bands. |
| `missing_parameters.csv` | missing | none | none | Missing inputs are embedded, not first-class. |
| `suggested_experiments.csv` | missing | none | none | Suggested experiments are embedded, not first-class. |
| `provenance_table.csv` | exists | `api/result_tables.py` | API/BIO tests | Good but should include output schema version. |
| `limitations_table.csv` | exists | `api/result_tables.py` | API/BIO tests | Strong, but some wording should be separated by source. |
| `environment_summary.csv` | exists | `api/result_tables.py` | ENV tests | Good metadata-only status; block rankings/heatmaps until active response. |
| `screen_summary.json` | exists | `screening/ensemble.py` | ensemble/API tests | Lower-layer summary; VE also writes `virtual_experiment_summary.json`. |

## Notebook Assessment

Reaction 618 notebook:

- Uses `VirtualExperiment`.
- Avoids direct `simulate_screen`, deterministic builder, and `run_configured_model`.
- Shows scientific underparameterization and exploratory run.
- Reads output tables.
- Clearly states limitations.

BIO-001 notebook:

- Uses `VirtualExperiment`.
- Runs scientific and exploratory preflight.
- Executes exploratory surface ensemble.
- Reads output tables and limitations.
- Adds a custom uncertainty-band plot from `time_series_long.csv`.
- Clearly states it is not whole-fungus growth.

Foundation notebooks:

- Use configured workflow public APIs.
- Are tested for smoke execution and hidden implementation patterns.

Notebook concern:

- `ruff check .` currently fails on notebook import-position `E402` errors, while `ruff check src tests` passes. The project should define notebook lint policy.

## Test-Suite Assessment

Strengths:

- Required VALIDATION-001 targeted tests pass.
- Full suite passes: `450 passed in 30.20s`.
- Tests cover registry loading, modelability, ensemble simulation, homogeneous Michaelis-Menten, surface catalysis, environment grids, virtual-experiment API, output tables, threshold metrics, provenance, scientific/exploratory separation, failure paths, and notebook smoke tests.

Gaps:

- Passing tests do not validate scientific predictions against experimental time courses.
- Output schema is not versioned as a data contract.
- Some tests assert existence/selected fields but not full publication schema completeness.
- There is no first-class test for `trajectory_quantiles.csv`, `missing_parameters.csv`, or `suggested_experiments.csv` because these outputs do not exist yet.
- There is no public scientific-mode `VirtualExperiment.simulate()` test because the API intentionally rejects it.

## Documentation And Progress Assessment

Strengths:

- The central virtual-experiment directive is clear and should remain the governing document.
- DATA-002, ENV-001, and BIO-001 progress files honestly describe scope and limitations.
- `data/README.md` and `data/experiments/README.md` clearly distinguish toy/synthetic/literature/validated maturity.
- `ARCHITECTURE_DEBT.md` exists and tracks active typing debt.

Concerns:

- README still points to old `foundation_progress/00...` documents that are no longer active in that location.
- The current active directive competes with old foundation-first wording unless contributors know to start from the central goal.
- A small `foundation_progress/README.md` would improve navigation.

## Hidden-Risk Assessment

High-signal hidden or easy-to-miss flaws:

- BIO-001 `soluble_product_concentration` has amount units, not concentration units.
- `accessible_site_fraction_remaining` is a proxy derived from substrate remaining, not a state evolved by a surface-accessibility mechanism.
- Environment-grid outputs can be compared across pH/temperature even though no environment response law is active.
- Broad SABIO-RK ranges are sampleable in exploratory mode and could be misused as calibrated uncertainty.
- `limitations_table.csv` can include preflight text saying no ODE was assembled, even in a simulated output bundle.
- State-role derivation in `result_tables.py` reads generated YAML sample configs, which is brittle for a standard output layer.
- Sample failures are captured broadly and only become blocking if all samples fail.
- Case-specific state names and time grids remain hardcoded in Python.
- Repo-wide ruff behavior differs from the configured `src tests` quality gate.

## Critical Blockers

1. Public scientific virtual experiments are not exposed through `VirtualExperiment.simulate()`.
2. Output observable semantics are not strict enough for publication tables, especially BIO-001 product concentration and accessible-site proxy.
3. Environment-grid metadata-only simulations must not be used for pH/temperature ranking.
4. Broad literature ranges need machine-readable interpretation before more data ingestion.
5. New biology would amplify schema and semantic debt before the current output layer is hardened.

## High-Priority Improvements

- Add output schema/data dictionary and schema-versioned table tests.
- Add public exact/scientific virtual-experiment simulation.
- Fix BIO-001 product amount/concentration semantics.
- Clarify or replace accessible-site proxy output.
- Add first-class missing-parameter and suggested-experiment tables.
- Add active guards against metadata-only environment ranking.

## Medium-Priority Improvements

- Move state names, product-map choices, and time-grid defaults into registry/config schemas.
- Add run-quality and partial-failure severity.
- Make summary tables self-contained or document joins.
- Separate preflight assumptions from simulation limitations.
- Clarify README/progress navigation.

## Low-Priority Improvements

- Decide notebook linting policy.
- Add optional table-derived quicklook uncertainty bands with maturity labels.
- Add environment heatmaps only after active environment-response support exists.

## What Must Not Be Built Next

- Do not add whole-fungus growth, secretion, uptake, biomass, respiration, or oxygen limitation next.
- Do not add new cellulose/lignocellulose mechanisms until BIO-001 output semantics are fixed.
- Do not use DATA-002 broad ranges as pH/temperature response curves.
- Do not ingest more datasets merely to decorate the registry.
- Do not polish plots as if they are the product before table semantics are stable.

## What Should Be Built Next

Recommended next milestone:

```text
SCHEMA-001 / API-002: output semantics, scientific-mode VirtualExperiment, and maturity-gate hardening
```

Minimum scope:

- versioned output schemas and data dictionary;
- public `simulate(mode="scientific")` for exact modelable cases;
- fixed BIO-001 product amount/concentration naming;
- explicit proxy vs modeled-state status for accessibility outputs;
- first-class `missing_parameters.csv` and `suggested_experiments.csv`;
- environment metadata-only comparison gate;
- README/progress entry-point cleanup.

## Milestone Assessment

API-001: substantially implemented for exploratory registry-ID virtual experiments and required tables. Not mature for exact scientific public API.

ENV-001: correctly implemented as metadata-only environment-grid expansion. Not an environment response model.

DATA-002: correctly implemented as local Reaction 618 multi-entry range curation with range/exact/prior distinctions. Needs stronger machine-readable range interpretation before more data.

BIO-001: correctly implemented as an exploratory enzyme-mediated cellulose-like surface pilot. Not scientifically validated; product and accessibility semantics need hardening before more biology.

## Final Recommendation

Do not proceed to new biology.

Do not proceed to broad new data ingestion.

Proceed to public API and output-schema hardening.

After SCHEMA-001 / API-002, the next safe data work should be validation-data candidate review, not mechanism expansion.

