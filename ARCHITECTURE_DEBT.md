# Architecture Debt Register:

This file is a containment mechanism, not permission to take shortcuts.

Temporary compromises are allowed only when they are documented here with an
ID, status, reason, risk, exit condition, removal milestone, and tests
protecting the boundary. New foundation work should remove entries from this
file, not normalize them.

Current state: two active contained entries, `FD-009` and `FD-010`. `FD-008` was resolved by shared
package integration on 2026-09-28. `FD-007` was
resolved on 2026-08-01 by deterministic build-time staging from the canonical
resource roots. `FD-005` was resolved in PR-41 by enabling Pyright optional-member-access
checking and narrowing nullable scientific values explicitly. `FD-006`
process-to-`Reaction` adapter debt was resolved in Phase 1 Task 4; retained
`Reaction`, `SimulationEngine`, and `ReactionDiffusionEngine1D` APIs are
intentional explicit low-level APIs, not native configured workflow
dependencies.

## FD-010 Per-candidate config rebuild in calibration and no parameter sensitivities

Status: active, contained since 2026-10-05 (BAYES-001)

Reason: `ConfiguredConditionPredictor` evaluates a candidate parameter vector
by rebuilding the condition's `ModelConfig` through a factory, reloading its
inputs, assembling the processes and recompiling the model before each
integration. This is deliberate: a registry template may bind a fitted symbol
into derived quantities (the culture template bakes the biomass yield into
product-map coefficients), and only the public build path puts the value
everywhere it belongs. The compiled core still offers no parameter
sensitivities or Jacobians, so posterior sampling is gradient-free and the
local identifiability diagnostic uses finite differences of the residuals.

Risk: roughly two thirds of a likelihood evaluation of the organism case is
rebuild overhead rather than integration, which caps chain lengths in a
session; without analytic sensitivities, gradient-based samplers and exact
Fisher information remain unavailable.

Containment: the predictor is the only calibration path onto the compiled
core and is tested for exact agreement with `run_configured_model`
(`tests/test_bayesian_calibration.py`,
`tests/test_gelain_bayesian_study.py`); the rebuild cost is recorded in the
ledger; the finite-difference step and eigenvalue cutoff of the local
information analysis are declared in every result.

Exit condition: compiled models expose parameter slots that kernels read at
evaluation time (with template-derived coefficients expressed as process
parameters rather than baked numbers), so a candidate vector updates a
compiled model in place; kernels supply state and parameter derivatives for
forward sensitivities.

Removal milestone: the compiled-core Jacobian item of FD-009's exit condition.

Tests protecting it:
`tests/test_bayesian_calibration.py::test_configured_predictor_matches_the_public_run_and_samples_a_toy_config`,
`tests/test_gelain_bayesian_study.py::test_predictor_reproduces_the_public_scientific_run_at_the_frozen_fit`.

## FD-009 Model representations and engines outside the compiled core

Status: active, contained since 2026-10-04 (CORE-001); narrowed 2026-10-05 (ORG-001, UNIFY-001)

Reason: `ProcessODESolver` now compiles `Process` models to a numeric
stoichiometric right-hand side with build-time unit resolution. Other
integration paths still own their own right-hand sides: the legacy
`Reaction`/`SimulationEngine` engine, the 1D and N-D reaction-diffusion
engines (which evaluate `Reaction` rate laws on unit-bearing quantities per
cell or per field), the research culture models, the legacy
`reactions()`/`build_engine()` path of `FungalCouplingModel` (kept for
caller-supplied `Reaction` rate laws), and the native `simulate` of
`ResourceLimitedCulture` and `DegradingCulture`, which the classes keep for
its analytic piecewise Jacobian. They predate the compiled core and are not
reachable from the registry-backed `VirtualExperiment` path.

Risk: scientific logic can drift between representations; spatial runs stay
too slow for calibration; a process without a numeric kernel could silently
keep the slow path; the two culture classes carry a second right-hand side
until the compiled core supplies a Jacobian.

Narrowing (ORG-001, 2026-10-05): the registry now reaches whole-organism
physiology through the generic `culture_physiology` template family and the
`proportional_synthesis` process, and `tests/test_organism_registry_case.py`
pins the registry composition of the Gelain hydrolysis candidate to the
research implementation in `research/gelain_models.py`. The research module
still owns its own right-hand side for the other candidates (published,
effective, retained); the Pirt/Monod closures with nitrogen and oxygen
limitation remain class-bound because no organism record parameterizes them.

Narrowing (UNIFY-001, 2026-10-05): the Pirt/Monod closure (growth after a
maintenance demand, capped maintenance, costed secretion sharing the
post-maintenance budget) and the chemostat exchanges (dilution against a feed,
gas transfer towards saturation) are generic processes in
`processes/culture.py` with factories and config support (`stoichiometry` on
`ProcessConfig`), exercised by the packaged
`toy_resource_limited_chemostat.yml` on abstract pools. `ResourceLimitedCulture`
and `DegradingCulture` emit them (`compiled_processes`, `compiled_parameters`)
and `simulate_compiled` integrates them on the compiled core; the parity
tests pin the compiled trajectories, extents, boundary ledgers and process
rates to the native `simulate` to 1e-7 relative and 1e-11 mol/L absolute at
tight tolerances. The classes keep `simulate` because its analytic piecewise
Jacobian is the one thing the compiled core cannot yet provide; both paths
name their engine in the trajectory diagnostics. `FungalCouplingModel`
composes `mass_action` (extended with catalysts), `first_order_decay` and
`proportional_synthesis` processes in `compiled_processes(degradation)` and
runs them through `simulate_compiled`, pinned to its legacy engine by
`tests/test_coupling_compiled.py`; the degradation must be supplied as
processes because a `Reaction`'s Python rate law cannot be compiled.

Narrowing (SPATIAL-001, 2026-10-06): the spatial mycelium core
(`fungal_model.mycelium`) compiles field processes to vectorised numpy
kernels with build-time unit resolution, conservative finite-volume
transport and the negative-state policy of the well-mixed core, so hyphal
growth no longer needs the `Reaction`-based engines; `tests/test_mycelium_core.py`
pins its diffusion operator to the transport engines' Laplacian. The 1D and
N-D reaction-diffusion engines remain the `Reaction` path for their own
cases, and the mycelium core does not yet lift well-mixed `Process` kernels
per cell nor supply a sparse compiled Jacobian; both are its next steps.

Containment: every shipped process and modifier compiles to a numeric kernel
and `tests/test_compiled_process_models.py` fails if one falls back; the
fallback path is recorded in `solver_metadata["kernel"]`, never silent; the
compiled path is tested for identical trajectories and evaluation counts
against the unit-aware evaluation on every packaged config; the culture
classes' compiled path is tested against their native path.

Exit condition: `Reaction` rate laws and the physiology classes are expressed
as processes (or builders) that emit the compiled representation; the spatial
engines apply compiled kernels per cell with vectorized diffusion; the legacy
`SimulationEngine` is retired; compiled models can supply a Jacobian (met,
opt-in, CORE-002: `CompiledModel.jacobian` from per-process gradients,
analytic for the simple laws and the closure, finite differences otherwise,
every kind recorded; the default stays the backend's differences so recorded
results do not move, which is also why the culture classes keep their native
path for now).

Removal milestone: completion of step 1 in
`foundation_progress/FUNGMOD_STATE_AND_NEXT_STEPS_2026-10-04.md`; step 2
(ORG-001) registered the first organism on the compiled core and the remaining
closures follow with the first organism that parameterizes them.

Tests protecting it: `tests/test_compiled_process_models.py`
(`test_shipped_process_types_all_compile_to_numeric_kernels`,
`test_process_without_kernel_uses_recorded_quantity_wrapped_path_exactly`),
`tests/test_organism_registry_case.py`
(`test_configured_model_reproduces_the_frozen_research_candidate`),
`tests/test_culture_processes.py`
(`test_resource_limited_culture_compiled_path_matches_the_native_right_hand_side`,
`test_degrading_culture_compiled_path_matches_the_native_right_hand_side`),
`tests/test_coupling_compiled.py`
(`test_coupling_compiled_path_matches_the_legacy_engine`).

## FD-008 Exploratory research-runner rate-law duplication

Status: resolved on 2026-09-28

Resolution: both runners now use `research.inhibited_progress`, a unit-aware
exploratory integration contract. The configured inhibition modifier and this
contract share the numeric denominator in `kinetics._coupled_inhibition`.
Sources and hypothesis rationale are required, stoichiometry is explicit,
solver failure is rejected, and concentration/time units are converted before
integration. Tests cover existing 2:1 source trajectories and an artificial 1:1
conservation case with a different initial product and time/unit choices.
The exponential activity-loss option remains a declared mathematical hypothesis;
it is not promoted to a validated thermal mechanism or registry default.

The original containment record follows for provenance.

Reason: the cross-source and mechanism-hypothesis research runners independently
integrate the published inhibited progress-curve law to fit candidate extensions.
They predate this containment entry and are not the public configured execution
path. Their deactivation extensions are explicit study hypotheses rather than
registered or validated biological mechanisms.

Risk: a standalone study can drift from the package law or promote numerical
fit quality to a mechanistic conclusion.

Containment: complete substrate and product trajectories from the cross-source
base law are compared to the current configured package model in tests. The
hypothesis runner compares its full reference trajectory at runtime and in tests.
Both runners reject solver/optimizer failure and protect the feasible nested
base fit. Reports state that mechanisms and identifiability are not established
by local training fits; the pNPG constant is not reused for cellobiose.

Exit condition: source the intended extension for one assay and express both
runners through a shared package/configured contract, retaining numerical parity
and negative-path tests without claiming broader biological applicability.

Removal milestone: the next bounded research-runner integration task, before
promoting any candidate extension into the registry or public configured API.

Tests protecting it: `tests/test_cross_source_structural_study.py` and
`tests/test_research_runner_guardrails.py`.

## FD-007 Wheel-packaged resource mirror

Status: resolved on 2026-08-01

Reason: setuptools package-data assets must live inside an installed package.
The repository's existing human-editable `data/` and `data_registry/` roots are
also used directly by tests, curation workflows, and contributor tooling, so
PUBLIC-RELEASE-001 mirrors their tracked files under
`src/fungal_model/_resources/` rather than moving the source-of-truth paths in
the release slice.

Risk: a contributor could update a registry, frozen source artifact, or example
config without updating the wheel mirror, producing checkout/install behavior
drift.

Exit condition: met. `setup.py` now uses the custom deterministic `build_py`
hook in `scripts/stage_packaged_resources.py` to stage the canonical `data/`
and `data_registry/` roots inside built wheels. `MANIFEST.in` includes those
canonical roots in source distributions, and source/editable checkouts resolve
them directly. The tracked `src/fungal_model/_resources/` mirror was removed.

Removal milestone: complete before the v0.1.1 release. Explicit writable-copy
semantics and cross-platform wheel paths remain unchanged.

Tests protecting it: `scripts/check_packaged_resources.py` stages into a clean
temporary tree and compares every canonical and staged file by relative path
and SHA-256 while rejecting a remaining source mirror;
`tests/test_packaged_distribution.py` runs that check and proves default
virtual-experiment, configured-model, and frozen-source workflows from outside
the checkout. CI builds both an sdist and wheel and runs an isolated installed-
wheel smoke.

## FD-001 Legacy PET workflow in the generic workflow package

Status: resolved in Milestone 9

Reason: `src/fungal_model/workflows/pet_surface_integration.py` predates the
generic configured-model workflow and is still needed by existing integration
tests.

Risk: PET remains visible from the generic workflow namespace and can keep
pulling high-level execution toward a substrate-specific path.

Exit condition: met. The PET convenience workflow moved to
`src/fungal_model/plugins/pet/workflows.py` and delegates to
`run_configured_model` with an explicit plugin registry. The generic
`src/fungal_model/workflows/` package no longer exposes PET workflow names or
imports low-level solvers.

Removal milestone: resolved in Milestone 9.

Tests protecting it: `tests/test_guardrails_no_hardcoding.py` no longer keeps
a PET allowlist for generic workflow paths, and
`tests/test_full_integration_workflow.py` verifies that the plugin convenience
helper still runs through the generic configured workflow.

## FD-002 PET-only substrate branch in YAML loading

Status: resolved in Milestone 3

Reason: `src/fungal_model/io/yaml_loader.py` had a PET-only `load_substrate`
implementation used by earlier config and workflow tests.

Risk: generic entity loading could stay hardcoded to one substrate and block
non-PET foundation benchmarks.

Exit condition: met. `load_substrate` now delegates to
`SubstrateLoaderRegistry`, the default registry loads generic benchmark
substrates, and PET loading requires an explicit plugin registry.

Removal milestone: resolved in Milestone 3.

Tests protecting it: `tests/test_guardrails_no_hardcoding.py` fails on
PET-specific lines in generic IO paths, and
`tests/test_registry_based_loading.py` verifies both default non-PET loading
and explicit PET plugin loading.

## FD-003 `AssembledModel.run()` native execution

Status: resolved in Milestone 7

Reason: `AssembledModel.run()` existed as a public method before native
process-centered ODE execution was available.

Risk: high-level workflows may continue manually constructing lower-level
solvers instead of routing through the assembled model.

Exit condition: met. `AssembledModel.run()` now delegates to
`ProcessODESolver`, builds derivatives from process `rate()` and
`contributions()`, records process-rate trajectories, runs validators, and
returns `fungal_model.results.SimulationResult`.

Removal milestone: resolved in Milestone 7.

Tests protecting it: `tests/test_native_assembled_model_run.py` verifies native
first-order and non-PET surface execution through `AssembledModel.run()`.
`tests/test_guardrails_no_shortcuts.py` no longer allows a public
`NotImplementedError` in `AssembledModel.run()`, and
`tests/test_guardrails_public_api.py` requires the generic public API names
without faking end-to-end execution.

## FD-004 Configured-model runner execution

Status: resolved in Milestone 8

Reason: Milestone 2 introduced `run_configured_model` as the generic public
entry point before registry-based entity loading, process-factory wiring,
native assembled-model execution, and configured output bundles exist.

Risk: users can see the correct generic entry point before it can execute a
model end to end.

Exit condition: met. `run_configured_model` loads entities through registries,
loads product maps, merges parameter sets with conflict detection, builds
processes through `ProcessLibrary`, assembles a `ModelBuilder`, calls
`AssembledModel.run()`, validates the result, and saves a standard output
bundle when an output directory is configured.

Removal milestone: resolved in Milestone 8.

Tests protecting it: `tests/test_configured_model_workflow.py` verifies that
the same generic runner executes the homogeneous, explicit-plugin, and dummy
non-plugin foundation configs. `tests/test_model_config_loading.py` verifies
that plugin loading requires an explicit registry instead of a generic
substrate-specific branch, and `tests/test_guardrails_public_api.py` keeps the
public entry point non-placeholder.

## FD-006 Process-to-Reaction compatibility adapters

Status: resolved in Phase 1 Task 4

Reason: Several concrete `Process` classes exposed `as_reaction()`
compatibility adapters that converted process-centered mechanisms into legacy
`Reaction` objects. These adapters predated native `ProcessODESolver` execution
and were later exercised only by direct low-level process tests.

Risk: Future high-level configured workflows could accidentally route native
`Process` objects through `Reaction`/`SimulationEngine` if these adapters are
treated as a main execution path instead of compatibility surface.

Exit condition: met. P1.4 proved the adapters had no supported production
workflow call sites, removed the concrete `as_reaction()` methods and shared
helper, and rewrote adapter-dependent tests to use native process execution or
direct `Reaction` construction where the retained low-level engine itself is
being tested.

Removal milestone: resolved in Phase 1 Task 4.

Tests protecting it: `tests/test_guardrails_native_execution.py` runs supported
configured well-mixed configs with tripwires on `SimulationEngine` and
`Reaction`, and asserts process modules no longer define `as_reaction()` or
`_reaction_from_process`. Direct low-level reaction-engine tests remain only
where `Reaction` objects are constructed explicitly.

## FD-005 Pyright optional-value baseline

Status: resolved in PR-41

Reason: before PR-41, Pyright checked invalid type forms, return types,
assignment types, argument types, attribute access, call issues, operator
issues, optional operands, and general type issues, but optional member access
remained disabled while scientific modules needed explicit non-null quantity
narrowing.

Risk before resolution: type checking could pass while optional
quantity/member-access issues remained in scientific modules. The enabled
diagnostic now protects that boundary.

Exit condition: met. Nullable quantity and parameter accesses now use explicit
narrowing or precise local annotations, and `reportOptionalMemberAccess` is
enabled while full Pyright remains green.

Removal milestone: resolved in PR-41.

Tests protecting it: `tests/test_quality_config.py` verifies that Pyright is a
declared dev dependency, that `pyrightconfig.json` exists, that
`reportOptionalMemberAccess` and the other stricter diagnostics are enabled,
and that CI runs the Pyright command. GitHub Actions runs Pyright on every push
and pull request.
