# VALIDATION-001 Proposed Changes

Date: 2026-06-07

These are recommendations only. No fixes were applied during VALIDATION-001.

## V001-PC001

Title: Add a versioned virtual-experiment output schema and data dictionary

Priority: critical

Category: outputs/API/science/tests

Reason: The output layer is the main product. Each table needs stable column definitions, units, maturity semantics, join keys, and not-applicable behavior.

Evidence from repo: API-001 writes the main requested tables, but state names and metrics are inferred from generated configs and process-specific code. Some recommended central-goal tables are missing or only embedded as columns.

Files likely affected: `src/fungal_model/api/result_tables.py`, `src/fungal_model/api/metrics.py`, `tests/test_virtual_experiment_api.py`, `tests/test_bio001_surface_cellulose_virtual_experiment.py`, new docs under active progress/docs.

Expected benefit: publication-oriented tables become inspectable, joinable, and resistant to overclaiming.

Risks: schema work can slow feature development; migration may require test updates.

Acceptance criteria: every standard output table has a documented schema, required columns, units policy, maturity fields, and tests for Reaction 618 and BIO-001.

Should this be done before new data ingestion? yes

Should this be done before new biology? yes

## V001-PC002

Title: Add public `VirtualExperiment.simulate(mode="scientific")` for exact modelable cases

Priority: high

Category: API/architecture/science

Reason: The public API currently simulates only exploratory ensembles, while deterministic scientific assembly exists below the public API.

Evidence from repo: `VirtualExperimentMode` is `Literal["exploratory"]`, and `_validate_simulation_mode()` rejects scientific mode.

Files likely affected: `src/fungal_model/api/virtual_experiment.py`, `src/fungal_model/screening/ensemble.py`, `src/fungal_model/screening/case_builder.py`, tests for Reaction 618 exact fixtures.

Expected benefit: exact curated cases can be run without being reframed as exploratory uncertainty screens.

Risks: scientific-mode result semantics must be strict; exact-but-unvalidated should not become "validated."

Acceptance criteria: a registry case with exact required parameters can run through `VirtualExperiment.simulate(mode="scientific")`, writes the same standard tables, and rejects uncertain/exploratory/toy values.

Should this be done before new data ingestion? yes

Should this be done before new biology? yes

## V001-PC003

Title: Rename or rederive BIO-001 `soluble_product_concentration`

Priority: critical

Category: science/outputs/API

Reason: BIO-001 uses a concentration word for a product state that is mass-equivalent and has mass units.

Evidence from repo: BIO-001 product state is named `soluble_product_concentration`; product units are inherited from the substrate state, currently kilograms.

Files likely affected: `src/fungal_model/screening/case_builder.py`, `src/fungal_model/api/result_tables.py`, `tests/test_bio001_surface_cellulose_virtual_experiment.py`, BIO-001 notebook.

Expected benefit: prevents a high-risk unit/observable misinterpretation in publication tables.

Risks: output filenames stay stable, but table rows and notebook text will need updates.

Acceptance criteria: BIO-001 reports either `soluble_product_amount` with kilogram units or a true concentration derived from amount and volume; tests assert name/unit consistency.

Should this be done before new data ingestion? yes

Should this be done before new biology? yes

## V001-PC004

Title: Make accessible-site output explicitly proxy-valued or implement a true state

Priority: high

Category: science/outputs

Reason: `accessible_site_fraction_remaining` sounds mechanistic but is currently derived from remaining substrate fraction.

Evidence from repo: result table generation computes the value as `substrate_value / initial_substrate`; surface process uses constant accessible surface area.

Files likely affected: `src/fungal_model/api/result_tables.py`, `src/fungal_model/processes/surface.py`, `data_registry/substrates/substrates.yml`, BIO-001 tests and notebook.

Expected benefit: prevents surface-accessibility overclaiming.

Risks: renaming may break downstream examples; implementing a real state requires new mechanism and parameters and should not be done casually.

Acceptance criteria: either the row is renamed as a proxy with `metric_status=derived_proxy`, or a true accessibility state is evolved with documented law, parameters, and tests.

Should this be done before new data ingestion? yes

Should this be done before new biology? yes

## V001-PC005

Title: Add first-class `missing_parameters.csv` and `suggested_experiments.csv`

Priority: high

Category: outputs/API

Reason: Central goal treats missing inputs and suggested experiments as standard researcher outputs, not only embedded columns.

Evidence from repo: suggested experiments are present in modelability report/case columns, but no dedicated tables are written by API-001.

Files likely affected: `src/fungal_model/api/result_tables.py`, `src/fungal_model/screening/modelability.py`, tests for underparameterized cases.

Expected benefit: improves experimental-design usefulness and makes underparameterized cases easier to analyze.

Risks: extra tables require clear not-applicable behavior for fully modelable cases.

Acceptance criteria: standard output folder includes schema-tested `missing_parameters.csv` and `suggested_experiments.csv`.

Should this be done before new data ingestion? yes

Should this be done before new biology? yes

## V001-PC006

Title: Gate metadata-only environment comparisons

Priority: high

Category: science/API/outputs

Reason: ENV-001 correctly records metadata-only status, but generated environment cases still produce comparable rows that can be ranked.

Evidence from repo: `EnvironmentGrid` overlays runtime environments and copies source parameter records while recording `environment_effect_status=metadata_only`.

Files likely affected: `src/fungal_model/api/environment_grid.py`, `src/fungal_model/api/result_tables.py`, `src/fungal_model/api/quicklook.py`, environment-grid tests.

Expected benefit: prevents pH/temperature response overclaiming.

Risks: users may expect environment grids to imply active effects; documentation needs to be crisp.

Acceptance criteria: metadata-only environment summaries include a non-ranking warning; environment heatmaps/rankings are blocked unless active response models or condition-specific parameters are present.

Should this be done before new data ingestion? yes

Should this be done before new biology? yes

## V001-PC007

Title: Move case-specific state names and time grids into registry/config schemas

Priority: medium

Category: architecture/API/outputs

Reason: Reaction 618 and BIO-001 are currently assembled through case-specific branches that hardcode state names and simulation horizons.

Evidence from repo: `case_builder.py` hardcodes `cellobiose_concentration`, `beta_D_glucose_concentration`, BIO-001 surface state names, and stop/points values.

Files likely affected: `data_registry/processes/process_compatibility.yml`, `data_registry/parameters/parameter_records.yml`, `src/fungal_model/screening/case_builder.py`, config schema/tests.

Expected benefit: adding a second real case becomes registry/config work rather than Python branching.

Risks: schema design can become overgeneralized if done before SCHEMA-001.

Acceptance criteria: process compatibility or a companion case schema declares state roles, observable names, product-map identity, and time grid defaults.

Should this be done before new data ingestion? no

Should this be done before new biology? yes

## V001-PC008

Title: Add run-quality and partial-failure severity to virtual-experiment outputs

Priority: medium

Category: API/outputs/tests

Reason: exploratory sample failures are captured and the run continues if at least one sample succeeds.

Evidence from repo: `simulate_screen()` catches `Exception` per sample and records `sample_failures`.

Files likely affected: `src/fungal_model/screening/ensemble.py`, `src/fungal_model/api/result_tables.py`, tests for partial failures.

Expected benefit: users can tell when an ensemble is mostly failed or numerically fragile.

Risks: stricter defaults may expose existing edge-case fragility.

Acceptance criteria: `case_summary.csv`, `limitations_table.csv`, and summary JSON report sample failure fraction and severity; configurable thresholds can fail a run.

Should this be done before new data ingestion? no

Should this be done before new biology? yes

## V001-PC009

Title: Separate preflight assumptions from simulation limitations

Priority: medium

Category: outputs/API/docs

Reason: the preflight phrase "no ODE model is assembled or run" appears inside simulated result limitations and can confuse users.

Evidence from repo: modelability assumptions are copied into `limitations_table.csv` for simulated cases.

Files likely affected: `src/fungal_model/screening/modelability.py`, `src/fungal_model/api/result_tables.py`, tests for limitations table text.

Expected benefit: limitations remain honest without implying that the simulation did not occur.

Risks: small wording change may require notebook/test updates.

Acceptance criteria: preflight assumptions are either isolated to `modelability_preflight.csv` or clearly labeled as preflight-only in the limitations table.

Should this be done before new data ingestion? no

Should this be done before new biology? yes

## V001-PC010

Title: Clarify README and progress-document entry points

Priority: medium

Category: docs

Reason: README points to old foundation-progress files that have been moved, while the active central directive is under `foundation_progress/`.

Evidence from repo: README references `foundation_progress/00_START_HERE_FOUNDATION_FIRST.md` and similar files; current historical docs are under `old_progress/`.

Files likely affected: `README.md`, `progress.md`, possibly `foundation_progress/README.md`.

Expected benefit: contributors start from the central virtual-experiment goal instead of stale foundation-only prompts.

Risks: documentation-only; low technical risk.

Acceptance criteria: README lists the active central directive first and explains that older progress files are archived under `old_progress/`.

Should this be done before new data ingestion? yes

Should this be done before new biology? yes

## V001-PC011

Title: Add explicit no-new-biology readiness gate

Priority: high

Category: science/tests/docs

Reason: BIO-001 is exploratory and useful, but new biology should not accumulate faster than validation and output semantics.

Evidence from repo: BIO-001 adds a controlled surface case, but product semantics, accessibility proxy status, and public scientific API remain immature.

Files likely affected: `tests/`, `foundation_progress/`, possible new validation gate test.

Expected benefit: protects the project from breadth-first biology expansion before the virtual-experiment engine is solid.

Risks: may slow visible feature expansion.

Acceptance criteria: a test or checklist fails new biology milestones unless they define outputs, parameters, provenance, limitations, and validation status.

Should this be done before new data ingestion? no

Should this be done before new biology? yes

## V001-PC012

Title: Add parameter-range interpretation fields

Priority: high

Category: data/science/outputs

Reason: `ValueSpec.range` does not encode whether a range is cross-entry literature spread, condition-specific range, posterior uncertainty, or user prior.

Evidence from repo: DATA-002 uses provenance notes to warn about all-eligible Reaction 618 ranges; this is correct but not machine-actionable enough.

Files likely affected: `data_registry/parameters/parameter_records.yml`, `src/fungal_model/registry/records.py`, `src/fungal_model/api/result_tables.py`, DATA-002 tests.

Expected benefit: prevents broad ranges from being used as calibrated uncertainty or environmental response.

Risks: schema migration may touch many tests.

Acceptance criteria: sampled-parameter outputs include range interpretation and allowed uses; scientific mode rejects inappropriate range interpretations.

Should this be done before new data ingestion? yes

Should this be done before new biology? yes

## V001-PC013

Title: Decide notebook linting policy

Priority: low

Category: tests/notebooks/docs

Reason: repo-wide ruff fails on notebooks, but configured `src tests` ruff passes.

Evidence from repo: `ruff check .` failed with 9 notebook `E402` errors during VALIDATION-001; `ruff check src tests` passed.

Files likely affected: `pyproject.toml`, notebooks, CI workflow, notebook tests.

Expected benefit: avoids contradictory quality-check reports.

Risks: linting notebooks can be noisy if path setup cells remain necessary.

Acceptance criteria: documentation and CI agree on whether notebooks are excluded from ruff or normalized to satisfy it.

Should this be done before new data ingestion? no

Should this be done before new biology? no

## V001-PC014

Title: Make summary tables self-contained or provide explicit join metadata

Priority: medium

Category: outputs/API

Reason: `summary_metrics.csv` is keyed by `case_id`, metric, and units; biological context is recoverable by join but not self-contained.

Evidence from repo: `summary_metrics.csv` construction groups only by `case_id`, metric, and units.

Files likely affected: `src/fungal_model/api/result_tables.py`, output table tests.

Expected benefit: tables are easier to analyze and cite without fragile manual joins.

Risks: wider tables duplicate context columns.

Acceptance criteria: every summary table includes fungus/substrate/environment/process context or ships a formal join/data dictionary.

Should this be done before new data ingestion? yes

Should this be done before new biology? yes

