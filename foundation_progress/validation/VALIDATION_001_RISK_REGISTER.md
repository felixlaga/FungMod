# VALIDATION-001 Risk Register

Date: 2026-06-07

Severity scale: critical, high, medium, low.

Likelihood scale: high, medium, low.

## Risks

### V001-R001: Exploratory priors may be mistaken for curated values

Severity: high

Likelihood: medium

Evidence: Reaction 618 and BIO-001 exploratory simulations run and produce full output tables. The tables do include `parameter_source_class` and limitations, but downstream users can still cite simulated outputs without reading provenance.

Why it matters scientifically: user-supplied priors are assumptions, not empirical cellulase or beta-glucosidase measurements.

Why it matters architecturally: a virtual-experiment engine must carry maturity and provenance through every researcher-facing output, not only through internal records.

Mitigation: add a stronger output schema/data dictionary, explicit run-level maturity banner, and fail/confirm behavior for publication export when any parameter is `exploratory_prior`.

Suggested next milestone: SCHEMA-001 / API-002 output semantics and maturity-gate hardening.

### V001-R002: Public virtual-experiment simulation supports exploratory mode only

Severity: high

Likelihood: high

Evidence: `VirtualExperimentMode = Literal["exploratory"]`; `_validate_simulation_mode()` rejects scientific simulation and says scientific deterministic experiments require a later public API.

Why it matters scientifically: exact modelable cases should be runnable without forcing users into an exploratory ensemble framing.

Why it matters architecturally: the lower deterministic builder can run exact scientific configs, but the public researcher API cannot expose that path yet.

Mitigation: add `VirtualExperiment.simulate(mode="scientific")` for exact-only modelable cases and preserve exact/scientific output provenance.

Suggested next milestone: API-002 scientific-mode virtual experiments.

### V001-R003: BIO-001 product state is called concentration while using mass units

Severity: high

Likelihood: high

Evidence: BIO-001 uses `soluble_product_concentration` as the product state, while the product state units are assigned from the substrate amount units (`kilogram`).

Why it matters scientifically: concentration implies amount per volume; reporting kilograms under a concentration name is publication-hostile and can cause misinterpretation.

Why it matters architecturally: output-state semantics are encoded in state names and tests rather than in a typed observable schema.

Mitigation: rename to `soluble_product_amount` or add volume-aware concentration calculation with explicit units.

Suggested next milestone: SCHEMA-001 output observable semantics.

### V001-R004: Accessible-site fraction is a derived proxy, not a simulated accessibility state

Severity: high

Likelihood: high

Evidence: `accessible_site_fraction_remaining` is computed as remaining substrate divided by initial substrate in `result_tables.py`; `SurfaceCatalysisProcess` uses constant accessible surface area and does not evolve morphology.

Why it matters scientifically: cellulose accessibility can change independently from total substrate mass through pore opening, enzyme erosion, crystallinity, swelling, or surface renewal.

Why it matters architecturally: derived proxies need explicit observable status so downstream metrics do not appear mechanistically richer than the model.

Mitigation: either rename the output to `remaining_substrate_fraction_proxy` or implement a true accessible-site state with parameters and tests.

Suggested next milestone: SCHEMA-001 before any new cellulose biology.

### V001-R005: Environment grids can be mistaken for environmental response models

Severity: high

Likelihood: medium

Evidence: ENV-001 correctly writes `environment_effect_status=metadata_only`, but generated pH/temperature cases still reuse parameter records and produce comparable trajectories.

Why it matters scientifically: users may rank temperatures or pH values even though no pH or temperature response law was applied.

Why it matters architecturally: environment metadata and active environment modifiers need separate schemas, metrics, and plot affordances.

Mitigation: add stronger warnings to environment summaries, suppress environment rankings/heatmaps for metadata-only grids, and require condition-specific parameters or response models before environmental comparison claims.

Suggested next milestone: ENV-002 response-model gate, after SCHEMA-001.

### V001-R006: Broad SABIO-RK ranges may be reused as calibrated uncertainty or response curves

Severity: high

Likelihood: medium

Evidence: DATA-002 correctly labels ranges as literature ranges across entries and not selected-entry uncertainty, but the same records are sampleable in exploratory mode.

Why it matters scientifically: cross-organism/cross-condition ranges are not posterior uncertainty for EntryID 35622 and are not pH/temperature functions.

Why it matters architecturally: `ValueSpec.range` does not itself encode whether the range is cross-entry, organism-specific, condition-specific, posterior, or user prior.

Mitigation: add `range_scope`, `range_interpretation`, and allowed-use policy to parameter records and sampled-parameter tables.

Suggested next milestone: DATA-003 parameter-range semantics, after output schema hardening.

### V001-R007: Case-specific state names and horizons are hardcoded in registry case assembly

Severity: medium

Likelihood: high

Evidence: `case_builder.py` hardcodes Reaction 618 state names and BIO-001 state names, time stops, and product-map naming.

Why it matters scientifically: output semantics can drift when adding the next substrate/process case.

Why it matters architecturally: the registry should describe observables, state roles, time grids, and product maps rather than relying on special-case Python branches.

Mitigation: move state-role names, default observables, and time-grid suggestions into registry/config schemas with tests.

Suggested next milestone: API-002 / REGISTRY-003 case schema generalization.

### V001-R008: Broad sample failure capture can hide degraded ensembles

Severity: medium

Likelihood: medium

Evidence: exploratory ensemble simulation catches `Exception` per sample, records failures, and proceeds if at least one sample succeeds.

Why it matters scientifically: a mostly failing ensemble may still emit tables and plots that look usable.

Why it matters architecturally: failure-rate thresholds and output warnings should be first-class result metadata.

Mitigation: add failure-rate severity, fail-fast options, and tests for partial failure reporting in `case_summary.csv`, `limitations_table.csv`, and `virtual_experiment_summary.json`.

Suggested next milestone: API-002 result quality gates.

### V001-R009: Modelability preflight limitation text can confuse simulated results

Severity: medium

Likelihood: medium

Evidence: modelability assumptions include "Modelability assessment only; no ODE model is assembled or run." These assumptions are copied into `limitations_table.csv` even for simulated virtual-experiment outputs.

Why it matters scientifically: users may read a simulated-result limitation row as saying no simulation was run.

Why it matters architecturally: preflight provenance needs a distinct table or clearer category/wording when embedded in simulation outputs.

Mitigation: revise wording to "preflight row only" or separate `modelability_preflight.csv` assumptions from simulation limitations.

Suggested next milestone: SCHEMA-001 table semantics.

### V001-R010: Recommended central-goal tables remain missing or partial

Severity: medium

Likelihood: high

Evidence: API-001 writes the required milestone tables, but central-goal recommended tables such as `trajectory_quantiles.csv`, `missing_parameters.csv`, and `suggested_experiments.csv` are not first-class outputs.

Why it matters scientifically: researchers need missing-parameter and suggested-experiment tables for experimental design, not only embedded columns.

Why it matters architecturally: standard result folders should be predictable and complete before new biology increases complexity.

Mitigation: implement the missing standard tables as schema-tested outputs.

Suggested next milestone: SCHEMA-001 output bundle completion.

### V001-R011: Documentation entry points are stale after progress-file relocation

Severity: medium

Likelihood: high

Evidence: README still references `foundation_progress/00_START_HERE_FOUNDATION_FIRST.md` and similar files, while historical progress files now live under `old_progress/`.

Why it matters scientifically: users may miss the central virtual-experiment directive and rely on obsolete foundation-first language.

Why it matters architecturally: validation and contributor workflow depend on unambiguous project directives.

Mitigation: update README to point to the active central directive and clarify `foundation_progress/` vs `old_progress/`.

Suggested next milestone: DOC-001 active directive cleanup.

### V001-R012: Notebook linting policy is ambiguous

Severity: low

Likelihood: high

Evidence: `ruff check .` fails with 9 `E402` notebook errors; `ruff check src tests` passes.

Why it matters scientifically: notebook drift can weaken reproducibility even when code tests pass.

Why it matters architecturally: CI and local validation should agree on whether notebooks are linted or only smoke-tested.

Mitigation: either exclude notebooks from repo-wide ruff or normalize notebook import cells and add a documented notebook lint gate.

Suggested next milestone: QA-001 notebook quality policy.

### V001-R013: BIO-001 has no empirical validation data

Severity: high

Likelihood: high

Evidence: BIO-001 uses user-supplied exploratory priors and explicitly states it is not validated against cellulose hydrolysis data.

Why it matters scientifically: the model is useful for output mechanics and hypothesis generation only; it cannot support empirical cellulose degradation claims.

Why it matters architecturally: the engine needs validation-data interfaces before adding more biological breadth.

Mitigation: do not add new cellulose mechanisms until output semantics are fixed; later add validation datasets only through candidate review, raw snapshot, curated mapping, and tests.

Suggested next milestone: SCHEMA-001 first; DATA-VALIDATION-001 later.

### V001-R014: Quick-look plots are useful but not publication-grade

Severity: low

Likelihood: high

Evidence: `quicklook.py` writes simple per-sample line plots from `time_series_long.csv`; uncertainty bands and environment heatmaps are absent from the API plot layer.

Why it matters scientifically: plots can visually imply maturity beyond the underlying exploratory model.

Why it matters architecturally: tables are the right primary output, but plot metadata and titles should reflect maturity and limitations.

Mitigation: keep plots optional, add maturity labels to plots, and only add environment heatmaps when environment effects are active.

Suggested next milestone: API-002 quicklook labeling after table schema hardening.

