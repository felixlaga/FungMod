# REAL-001 SABIO-RK Reaction 618 Progress

## Status

Status: REAL-001G-REVIEW complete. The native SABIO-RK Reaction 618 homogeneous Michaelis-Menten exploratory ensemble workflow is verified. No new data searching, biological mechanisms, or SABIO-RK records were added during this review.

## Current phase

Current phase: REAL-001G-REVIEW complete on 2026-06-05.

## Completed phases

- REAL-001A: Fetch raw SABIO-RK Reaction 618 kinetic-law export
- REAL-001B: Parse export and select one kinetic-law entry
- REAL-001C: KineticRecord schema and curated record
- REAL-001D: Registry integration
- REAL-001E: Homogeneous Michaelis-Menten registry case builder
- REAL-001F: Notebook and final reporting
- REAL-001G: Native homogeneous Michaelis-Menten exploratory ensemble support

## Incomplete phases

- None for REAL-001G.

## REAL-001G-REVIEW: Native Reaction 618 workflow verification

Status: complete.

Scope:

- Review only.
- No new dataset search.
- No new biological mechanisms.
- No new SABIO-RK records.
- Existing Reaction 618 range files were reviewed only as already-present local registry state.

Completed REAL-001G work verified:

- Scientific mode remains underparameterized for Reaction 618 because selected SABIO-RK EntryID `35622` has no usable `enzyme_concentration_beta_glucosidase`.
- The literature-processed enzyme concentration record is still:
  - `record_id: sabiork_reaction_618_enzyme_concentration_beta_glucosidase`
  - `value.kind: unknown`
  - `confidence_level: missing_from_selected_entry`
- Scientific modelability filters out exploratory parameter records and reports `enzyme_concentration_beta_glucosidase` as missing.
- Exploratory mode uses only the explicitly marked exploratory enzyme-concentration prior:
  - `record_id: exploratory_reaction_618_enzyme_concentration_beta_glucosidase_loguniform`
  - `maturity: exploratory_prior`
  - `provenance.exploratory_prior: true`
  - `source: user-supplied exploratory range`
  - `confidence_level: exploratory_assumption`
  - loguniform range `1.0e-6` to `1.0e-3 mM`
- `simulate_screen(...)` runs the `homogeneous_michaelis_menten` case directly through the process assembler path:
  - `select_registry_case_compatibility(...)`
  - `get_registry_process_assembler("homogeneous_michaelis_menten")`
  - `build_registry_process_config_data(...)`
  - `run_configured_model(...)`
- `final_states.csv` contains scalar final values, not trajectory lists.
- `sampled_parameters.csv` includes sampled `enzyme_concentration_beta_glucosidase`.
- Per-sample trajectory CSV files are written under the case trajectory directory.
- Screen-level outputs are written:
  - `screen_summary.json`
  - `sampled_parameters.csv`
  - `final_states.csv`
  - `sample_failures.csv`
  - `sampled_parameter_summary.csv`
  - `final_state_summary.csv`
- Existing `surface_catalysis` ensemble behavior still passes.

Incomplete REAL-001G work:

- No curated/literature enzyme concentration was added for `enzyme_concentration_beta_glucosidase`.
- No deterministic scientific Reaction 618 build is possible for the default selected case while enzyme concentration remains unknown.
- No aggregate trajectory quantile output is written.
- No time-course validation dataset exists for Reaction 618.

Architecture debt:

- Initial substrate and enzyme concentrations are still represented as registry parameter records rather than first-class initial-state records.
- `RegistryProcessAssembler` is a lightweight internal metadata registry, not a full plugin/process assembly interface.
- Aggregate trajectory quantiles are not written.
- Bare `pytest` on this machine resolves to macOS Python 3.9, which is incompatible with the current code's `typing.TypeAlias` import; the project venv is required for valid test execution.

Data debt:

- `enzyme_concentration_beta_glucosidase` remains missing from selected SABIO-RK EntryID `35622`.
- The exploratory enzyme-concentration range is user-supplied and marked as exploratory; it is not SABIO-RK-curated or literature-curated.
- The pilot is enzyme-only soluble kinetics, not a full fungus model.
- No secretion, uptake, biomass, oxygen limitation, PET chemistry, cellulose morphology, or time-course validation data are represented in REAL-001G.

Premature REAL-002A work already added:

- The repository already contains local Reaction 618 literature-range work beyond REAL-001G:
  - `data/kinetic_records/sabiork/case_001_reaction_618_beta_glucosidase/curated/parameter_range_summary.json`
  - `sabiork_reaction_618_literature_range_Km_cellobiose`
  - `sabiork_reaction_618_literature_range_kcat_cellobiose`
- Those records summarize eligible entries from the saved local SABIO-RK export only; they were not added during REAL-001G-REVIEW.
- The range records are broad across eligible entries and are not calibrated to one organism, enzyme variant, pH, temperature, or assay condition.
- The range records do not solve the missing enzyme-concentration blocker.
- This review did not remove the premature REAL-002A work because it is existing repository state and the current task is review-only.

Review test commands and exact results:

- `pytest tests/test_sabiork_reaction_618_registry_case.py`
  - Result: failed during collection under Python `3.9.6` with `ImportError: cannot import name 'TypeAlias' from 'typing'`; `0` items collected, `1` error.
- `pytest tests/test_registry_ensemble_homogeneous_mm.py`
  - Result: failed during collection under Python `3.9.6` with `ImportError: cannot import name 'TypeAlias' from 'typing'`; `0` items collected, `1` error.
- `pytest tests/test_registry_ensemble_simulation.py`
  - Result: failed during collection under Python `3.9.6` with `ImportError: cannot import name 'TypeAlias' from 'typing'`; `0` items collected, `1` error.
- `pytest`
  - Result: failed during collection under Python `3.9.6`; `21` items collected before interruption, `57` collection errors, all from `ImportError: cannot import name 'TypeAlias' from 'typing'`.

Project venv verification:

- `.venv/bin/python -m pytest tests/test_sabiork_reaction_618_registry_case.py`
  - Result: `16 passed in 9.31s`
- `.venv/bin/python -m pytest tests/test_registry_ensemble_homogeneous_mm.py`
  - Result: `3 passed in 14.28s`
- `.venv/bin/python -m pytest tests/test_registry_ensemble_simulation.py`
  - Result: `6 passed in 10.88s`
- `.venv/bin/python -m pytest`
  - Result: `428 passed in 35.84s`

Runtime output smoke check:

- Ran a local two-sample `simulate_screen(...)` smoke check using the existing registry.
- Confirmed process type `homogeneous_michaelis_menten`.
- Confirmed `sampled_parameters.csv` includes `enzyme_concentration_beta_glucosidase`.
- Confirmed `final_states.csv` final-state values are scalar strings/values, not list literals.
- Confirmed two per-sample trajectory CSV files were written.
- Confirmed `sampled_parameter_summary.csv`, `final_state_summary.csv`, and `sample_failures.csv` were written.
- Confirmed `sample_failures.csv` had zero failure rows for the smoke check.

## What is done

- Scientific Reaction 618 modelability remains underparameterized because SABIO-RK EntryID `35622` does not provide `enzyme_concentration_beta_glucosidase`.
- Added a separate exploratory prior record for `enzyme_concentration_beta_glucosidase`:
  - `maturity: exploratory_prior`
  - `source: user-supplied exploratory range`
  - `confidence_level: exploratory_assumption`
  - `distribution: loguniform`
  - range: `1.0e-6` to `1.0e-3 mM`
- Scientific mode ignores exploratory prior records.
- Exploratory mode can select the marked prior and classify Reaction 618 as exploratory rather than underparameterized.
- `simulate_screen(...)` now dispatches exploratory ensemble runs by process type.
- Existing `surface_catalysis` ensemble behavior still passes.
- Added native `homogeneous_michaelis_menten` ensemble support using the existing registry case-builder config path.
- Per-sample configs are generated from sampled exact parameter records.
- Per-sample runs are executed through `run_configured_model(...)`.
- Successful samples save sampled parameters, scalar final states, and trajectory CSVs.
- Sample failures are collected without aborting the whole screen unless all samples fail.
- Screen-level CSV outputs are written:
  - `sampled_parameters.csv`
  - `final_states.csv`
  - `sample_failures.csv`
  - `sampled_parameter_summary.csv`
  - `final_state_summary.csv`
- The Reaction 618 notebook now calls `simulate_screen(...)` directly and no longer manually edits YAML or runs a notebook-local ensemble loop.

## What is not done

- The unknown SABIO-RK enzyme concentration was not converted into a curated value.
- No live SABIO-RK API access was added outside fetch scripts.
- No bulk SABIO-RK import was added.
- No fungus growth, secretion, uptake, biomass, oxygen limitation, PET chemistry, cellulose surface morphology, or time-course validation model was added.
- No aggregate `trajectory_quantiles.csv` writer was added.

## Data fetched or generated

- No new live SABIO-RK data was fetched.
- No new literature value was curated.
- Added one user-supplied exploratory prior record for sensitivity analysis only:
  - `exploratory_reaction_618_enzyme_concentration_beta_glucosidase_loguniform`
- Tests generated temporary screen outputs under pytest temporary directories only.
- Notebook smoke tests generated temporary screen outputs through `FUNGMOD_NOTEBOOK_OUTPUT_ROOT`.
- No generated screen output files were committed.

## Selected SABIO-RK EntryID

- `35622`

## Selected organism

- `Oryza sativa`

## Selected kinetic law type

- `Michaelis-Menten`

## Selected parameters

- `Km_cellobiose`: exact `15.3 mM`
- `kcat_cellobiose`: exact `0.13 s^(-1)`
- `initial_cellobiose_concentration`: exact `3.06 mM`
- `enzyme_concentration_beta_glucosidase`: unknown in the selected SABIO-RK entry
- Exploratory-only prior for `enzyme_concentration_beta_glucosidase`: loguniform `1.0e-6` to `1.0e-3 mM`

## Scientific modelability result

- Default Reaction 618 registry case in scientific mode:
  - status: `underparameterized`
  - required process: `homogeneous_michaelis_menten`
  - missing parameter: `enzyme_concentration_beta_glucosidase`
- Deterministic build remains blocked for the default real case because enzyme concentration is unknown.

## Exploratory ensemble result

- Default Reaction 618 registry case in exploratory mode:
  - status: `exploratory`
  - selected uncertain parameter: `enzyme_concentration_beta_glucosidase`
  - selected record: `exploratory_reaction_618_enzyme_concentration_beta_glucosidase_loguniform`
- `simulate_screen(...)` ran a 32-sample homogeneous Michaelis-Menten Reaction 618 ensemble successfully in tests.
- Sampled enzyme concentrations stayed within `[1.0e-6, 1.0e-3] mM`.
- Fixed-seed runs reproduced the same sampled enzyme concentrations.
- `final_states.csv` stores scalar final values, not full trajectory lists.

## Files changed

- `data_registry/parameters/parameter_records.yml`
- `foundation_progress/REAL_001_SABIO_RK_PROGRESS.md`
- `notebooks/06_sabiork_reaction_618_beta_glucosidase.ipynb`
- `src/fungal_model/screening/__init__.py`
- `src/fungal_model/screening/ensemble.py`
- `src/fungal_model/screening/modelability.py`
- `tests/test_sabiork_reaction_618_notebook.py`
- `tests/test_sabiork_reaction_618_registry_case.py`

## Files added

- `tests/test_registry_ensemble_homogeneous_mm.py`

## Tests added

- Homogeneous Michaelis-Menten exploratory ensemble run success for Reaction 618.
- Sampled enzyme concentrations stay within the exploratory range.
- Fixed-seed homogeneous ensemble reproducibility.
- Ensemble refusal when the exploratory enzyme prior is absent.
- Scalar final-state CSV output checks.
- Notebook smoke test now executes the direct `simulate_screen(...)` path.
- Registry/modelability tests now distinguish the literature unknown enzyme record from the exploratory prior record.

## Tests run

- `.venv/bin/python -m pytest tests/test_sabiork_reaction_618_registry_case.py tests/test_registry_ensemble_homogeneous_mm.py tests/test_registry_ensemble_simulation.py tests/test_sabiork_reaction_618_notebook.py -q`
  - Result: `29 passed in 21.86s`
- `.venv/bin/python -m pytest -q`
  - Result: `418 passed in 33.17s`

## What failed

- Initial focused run failed because the notebook fixture-path assertion expected the old single-line path literal.
- The notebook test was corrected to check the local fixture path components.
- No tests failed after that correction.

## Architecture debt added

- Initial substrate and enzyme concentrations are still represented as required registry parameters because there is no first-class registry state-initialization record type.
- Per-sample trajectories are saved, but aggregate trajectory quantiles are not yet written.

## ARCH-001 follow-up: Ensemble process assembler interface

Status: complete.

What changed:

- Added `RegistryProcessAssembler` metadata in `src/fungal_model/screening/case_builder.py`.
- Centralized supported process metadata for:
  - `surface_catalysis`
  - `homogeneous_michaelis_menten`
- Routed deterministic registry-case building through the assembler metadata.
- Routed exploratory `simulate_screen(...)` through the same assembler metadata.
- Removed direct private case-builder helper imports from `ensemble.py`.
- Removed process-specific ensemble handler duplication from `ensemble.py`.
- Added architecture guardrail tests that assert `ensemble.py` uses the assembler API instead of importing private config-data helpers.

Tests run for ARCH-001 follow-up:

- `.venv/bin/python -m pytest tests/test_registry_case_builder.py tests/test_registry_ensemble_simulation.py tests/test_registry_ensemble_homogeneous_mm.py tests/test_sabiork_reaction_618_registry_case.py -q`
  - Result: `33 passed in 17.59s`

Architecture debt remaining after ARCH-001 follow-up:

- `RegistryProcessAssembler` is still a lightweight internal metadata registry, not a full plugin interface.
- Config-data builders remain in `case_builder.py`; future process families may need a dedicated process-assembler module before this file grows further.
- Initial-state values still use parameter records rather than first-class state-initialization registry records.
- Aggregate trajectory quantiles are still not written.

## REAL-002A follow-up: Literature Km/kcat ranges from local SABIO-RK export

Status: complete.

What changed:

- Added local curation support for Reaction 618 `Km_cellobiose` and `kcat_cellobiose` ranges.
- Added `curated/parameter_range_summary.json`, generated only from the saved raw export.
- Added two broad registry range records:
  - `sabiork_reaction_618_literature_range_Km_cellobiose`
  - `sabiork_reaction_618_literature_range_kcat_cellobiose`
- Added parser/report tests for the saved raw export.
- Added registry tests proving exact selected-entry records and broad literature-range records coexist.
- Updated parameter-record selection so scientific mode prefers exact records over literature ranges when both are available for the same symbol.

Eligibility criteria:

- local saved SABIO-RK Reaction 618 export only;
- plain `Michaelis-Menten` kinetic-law entries only;
- EC `3.2.1.21`;
- enzyme name containing beta-glucosidase;
- Cellobiose substrate and beta-D-Glucose/glucose product;
- explicit paired `Km` and `kcat`;
- `Km` units exactly `mM`;
- `kcat` units exactly `s^(-1)`;
- no unit conversion.

Curated range result:

- Included EntryIDs: `35622`, `38521`, `38523`, `38524`, `38525`, `38526`, `38527`, `39780`, `39781`, `39782`, `39783`, `39784`, `44879`, `44888`, `60725`.
- `Km_cellobiose`: `0.68` to `114.0 mM`, `n = 15`.
- `kcat_cellobiose`: `0.13` to `7.17 s^(-1)`, `n = 15`.

Tests run for REAL-002A:

- `.venv/bin/python -m pytest tests/test_sabiork_parser.py -q`
  - Result: `11 passed in 0.50s`
- `.venv/bin/python -m pytest tests/test_sabiork_parser.py tests/test_sabiork_reaction_618_registry_case.py tests/test_modelability_report.py tests/test_registry_ensemble_homogeneous_mm.py tests/test_sabiork_reaction_618_notebook.py -q`
  - Result: `42 passed in 19.48s`

Architecture debt remaining after REAL-002A:

- Literature ranges are curated as broad registry parameter records and do not yet have a dedicated user-facing override mechanism for ensembles.
- The curation criteria are Reaction 618-specific, not a generic SABIO-RK range importer.

Data debt remaining after REAL-002A:

- The ranges summarize eligible saved SABIO-RK entries, but they are not calibrated to one organism, enzyme variant, pH, temperature, or assay condition.
- pH-dependent Michaelis-Menten entries were excluded from this first range curation pass.
- Enzyme concentration remains unknown in selected EntryID `35622`; no enzyme-concentration value was curated or inferred.

## REAL-002B follow-up: Time-course dataset candidate review

Status: candidate selected for schema review; observations not ingested.

What changed:

- Added a schema-first dataset candidate review:
  - `data/experiments/candidate_reviews/resa_buckin_2011_cellobiose_hydrolysis_review.yml`
- Updated candidate-review tests so the new real literature candidate loads and remains free of observations, CSV paths, measurements, and extracted rows.
- Updated `data/experiments/candidate_reviews/README.md` to state that the real candidate is not yet an ingested dataset.

Candidate source:

- Resa P, Buckin V. Ultrasonic analysis of kinetic mechanism of hydrolysis of cellobiose by beta-glucosidase. `Anal Biochem`. 2011;415(1):1-11.
- DOI: `10.1016/j.ab.2011.03.003`
- PubMed: `https://pubmed.ncbi.nlm.nih.gov/21385562/`

Why selected:

- PubMed abstract reports real-time HR-US monitoring of cellobiose hydrolysis by `Aspergillus niger` beta-glucosidase at 50 C and pH 4.9.
- The abstract states that glucose release time profiles and reaction-rate time profiles were obtained.
- The abstract states that the HR-US results agree with a discontinuous glucose assay.

What remains incomplete:

- No full-text figure/table values were extracted.
- No `ExperimentDataset` was created under `data/experiments/literature/`.
- No CSV observations were added.
- No comparison, calibration, or validation run was performed.
- Units, uncertainty, preprocessing, and digitization rules still need schema review.

Tests run for REAL-002B candidate selection:

- `.venv/bin/python -m pytest tests/test_dataset_candidate_review.py -q`
  - Result: `12 passed in 0.39s`

## REAL-002C follow-up: Literature-schema extraction decision

Status: complete; ingestion blocked pending full extraction metadata.

What changed:

- Updated `data/experiments/candidate_reviews/resa_buckin_2011_cellobiose_hydrolysis_review.yml` with a `schema_review` section.
- Changed candidate `review.schema_result` to `blocked_missing_extraction_metadata`.
- Added tests proving the candidate remains blocked from ingestion and contains no observations or measurement rows.

Decision:

- `blocked_do_not_ingest`

Reason:

- PubMed metadata and abstract are sufficient to identify a promising source, but not sufficient to create an `ExperimentDataset`.
- Required metadata is still missing:
  - exact figure/table identifier for extractable observations;
  - extraction method and extraction tool;
  - extracted_by and extraction_date;
  - raw time/value units for extracted rows;
  - uncertainty definition;
  - digitization, table, or supplementary-data provenance;
  - preprocessing steps and excluded-point decisions;
  - machine-readable observation CSV.

No data added:

- No full-text figure/table values were extracted.
- No `data/experiments/literature/` dataset file was created.
- No observation CSV was created.
- No comparison, calibration, or validation was run.

Tests run for REAL-002C:

- `.venv/bin/python -m pytest tests/test_dataset_candidate_review.py tests/test_literature_schema_contract.py -q`
  - Result: `26 passed in 0.42s`

## REAL-002D follow-up: Full-text and supplementary access review

Status: complete for access review; ingestion remains blocked.

What is done:

- Checked the selected Resa and Buckin 2011 candidate for accessible full-text/supplementary observation data.
- Added an `access_review` section to `data/experiments/candidate_reviews/resa_buckin_2011_cellobiose_hydrolysis_review.yml`.
- Recorded PubMed, ScienceDirect, and web-search checks for the candidate source.
- Kept the candidate blocked from ingestion because no machine-readable supplementary data, numeric observation rows, or digitization-ready figure/table metadata were found in public checks.
- Added a test proving the access review keeps ingestion blocked and contains no embedded observations, measurements, data file, or CSV path.

What is not done:

- No full-text figure/table values were extracted.
- No supplementary observation file was found or imported.
- No `ExperimentDataset` was created under `data/experiments/literature/`.
- No observation CSV was created.
- No comparison, calibration, validation, or model-fitting run was performed.

Decision:

- `keep_candidate_blocked_do_not_ingest`

Tests run for REAL-002D:

- `.venv/bin/python -m pytest tests/test_dataset_candidate_review.py tests/test_literature_schema_contract.py -q`
  - Result: `27 passed in 0.51s`
- `.venv/bin/python -m pytest tests/test_dataset_candidate_review.py tests/test_literature_schema_contract.py tests/test_experiment_dataset_loading.py tests/test_experiment_dataset_validation_rules.py tests/test_sabiork_reaction_618_registry_case.py -q`
  - Result: `62 passed in 9.12s`
- `.venv/bin/python -m pytest -q`
  - Result: `425 passed in 32.90s`
- `git diff --check`
  - Result: passed with no output

What failed:

- No tests failed during REAL-002D implementation.

Architecture debt added:

- None. REAL-002D only records access-review metadata and test guardrails.

Data debt added:

- The selected time-course candidate still lacks extractable numeric observations in the repository.
- Public checks did not identify a machine-readable supplementary file or observation CSV.
- The repository still has no literature time-course validation dataset for Reaction 618.

## REAL-002E follow-up: Alternate public time-course candidate selection

Status: complete for alternate candidate selection; ingestion remains blocked.

What is done:

- Selected a second public literature candidate for future beta-glucosidase/cellobiose time-course review:
  - `data/experiments/candidate_reviews/ariaeenejad_2020_persibgl1_cellobiose_hydrolysis_review.yml`
- Recorded Frontiers HTML/PDF source metadata for:
  - Ariaeenejad S, Nooshi-Nedamani S, Rahban M, Kavousi K, Pirbalooti AG, Mirghaderi S, Mohammadi M, Mirzaei M, Salekdeh GH. `A Novel High Glucose-Tolerant beta-Glucosidase Targeted Computational Approach for Metagenomic Screening`. `Front Bioeng Biotechnol`. 2020;8:813.
  - DOI: `10.3389/fbioe.2020.00813`
- Recorded that the article identifies a specific time-course target:
  - Figure 6, glucose yield during PersiBGL1 hydrolysis of cellobiose.
- Recorded assay metadata available from the source review:
  - cellobiose substrate;
  - PersiBGL1 enzyme;
  - 50 mM phosphate buffer;
  - pH 8;
  - 40 C;
  - glucose detection by glucose oxidase-peroxidase method from the method text.
- Updated candidate-review tests and README.
- Kept `data/experiments/literature/` empty of real paper data.

What is not done:

- Figure 6 was not digitized.
- No time/glucose-yield rows were extracted.
- No machine-readable observation CSV was found or created.
- No `ExperimentDataset` was created.
- No uncertainty model, preprocessing, excluded-point policy, or digitization metadata was created.
- The source's time-unit inconsistency was not resolved: method/caption refer to hours, while nearby result text also says `380 min`.

Decision:

- `select_candidate_for_schema_review_do_not_ingest`

Tests run for REAL-002E:

- `.venv/bin/python -m pytest tests/test_dataset_candidate_review.py -q`
  - Result: `16 passed in 0.43s`
- `.venv/bin/python -m pytest tests/test_dataset_candidate_review.py tests/test_literature_schema_contract.py tests/test_experiment_dataset_loading.py tests/test_experiment_dataset_validation_rules.py -q`
  - Result: `48 passed in 0.49s`
- `.venv/bin/python -m pytest -q`
  - Result: `427 passed in 32.82s`

What failed:

- No tests failed during REAL-002E implementation.

Architecture debt added:

- None. REAL-002E only adds candidate-review metadata and tests.

Data debt added:

- The new candidate is figure-based, not table- or CSV-based.
- Figure 6 requires a future digitization protocol before any observation data can be used.
- Time-axis units must be resolved before ingestion.
- No literature time-course validation dataset exists yet.

## REAL-002F follow-up: Figure 6 time-axis ambiguity decision

Status: complete; digitization and ingestion remain blocked.

What is done:

- Reviewed the Ariaeenejad 2020 PersiBGL1 Figure 6 time-axis evidence before digitization.
- Added a `digitization_review` section to `data/experiments/candidate_reviews/ariaeenejad_2020_persibgl1_cellobiose_hydrolysis_review.yml`.
- Updated the candidate top-level `review.schema_result` to:
  - `blocked_time_axis_conflict`
- Recorded conflicting source evidence:
  - method text says samples were collected in `24-h` intervals until `380 h`;
  - Figure 6 caption says `380 h`;
  - result text says glucose from `1 h` to `380 h` and little change after `300 h`;
  - result text also says conversion reaches zero after `380 min`.
- Added tests proving the unresolved source conflict blocks digitization and dataset creation.
- Kept `data/experiments/literature/` empty of real paper data.

What is not done:

- Figure 6 was not digitized.
- No time-axis unit was chosen by inference.
- No time/glucose-yield observation rows were extracted.
- No observation CSV was created.
- No `ExperimentDataset` was created.
- No comparison, calibration, or validation run was performed.

Decision:

- `blocked_time_axis_conflict_do_not_ingest`

Reason:

- The source itself contains conflicting time-axis statements. Choosing hours because most source statements use hours would still be an inference, not source-resolved metadata.

Tests run for REAL-002F:

- `.venv/bin/python -m pytest tests/test_dataset_candidate_review.py -q`
  - Result: `17 passed in 0.50s`
- `.venv/bin/python -m pytest tests/test_dataset_candidate_review.py tests/test_literature_schema_contract.py tests/test_experiment_dataset_loading.py tests/test_experiment_dataset_validation_rules.py -q`
  - Result: `49 passed in 0.48s`
- `.venv/bin/python -m pytest -q`
  - Result: `428 passed in 32.00s`

What failed:

- No tests failed during REAL-002F implementation.

Architecture debt added:

- None. REAL-002F only adds candidate-review metadata and tests.

Data debt added:

- The Ariaeenejad Figure 6 candidate cannot be digitized safely without resolving the time-axis conflict.
- No raw author-supplied data, erratum, or machine-readable time-course file is present in the repository.
- No literature time-course validation dataset exists yet.

## Data debt added

- REAL-002A added literature-derived broad Km/kcat range records from the saved local SABIO-RK export.
- Remaining data debt:
  - `enzyme_concentration_beta_glucosidase` is not supplied by SABIO-RK EntryID `35622`;
  - the `1.0e-6` to `1.0e-3 mM` enzyme-concentration range is user-supplied and exploratory, not literature-curated;
  - literature Km/kcat ranges are broad across eligible entries and are not condition-specific calibrated priors;
  - the REAL-002B/REAL-002C time-course source is only a candidate review with a blocked extraction decision; no observation values have been extracted;
  - no time-course validation dataset is used;
  - this is an enzyme-only kinetic pilot, not a living fungus growth model;
  - no secretion, uptake, biomass, oxygen, PET chemistry, or cellulose morphology data are represented.
  - the REAL-002D access review kept the selected time-course candidate blocked because no publicly accessible machine-readable observations or supplementary data were found.
  - the REAL-002E alternate source is public and figure-targeted, but still lacks digitized rows, uncertainty, preprocessing, and resolved time-axis units.
  - the REAL-002F digitization review blocks the Ariaeenejad Figure 6 source because its time-axis units conflict in source text.

## Known limitations

- The Reaction 618 records describe a soluble enzyme kinetics case, not whole-fungus degradation.
- The exploratory ensemble is a sensitivity analysis over one missing enzyme concentration parameter.
- The current pilot does not validate predicted trajectories against observations.

## Next recommended phase

Recommended next phase: REAL-002G, to search for a beta-glucosidase/cellobiose time-course source with tabular or machine-readable observations, or obtain author-supplied raw Figure 6 data/erratum for Ariaeenejad 2020. Do not create a `literature_raw` `ExperimentDataset` until units, uncertainty, preprocessing, extraction, and provenance metadata are complete.
