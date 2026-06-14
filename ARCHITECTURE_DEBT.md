# Architecture Debt Register:

This file is a containment mechanism, not permission to take shortcuts.

Temporary compromises are allowed only when they are documented here with an
ID, status, reason, risk, exit condition, removal milestone, and tests
protecting the boundary. New foundation work should remove entries from this
file, not normalize them.

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

Status: active

Reason: Several concrete `Process` classes still expose `as_reaction()`
compatibility adapters that convert process-centered mechanisms into legacy
`Reaction` objects. These adapters predate native `ProcessODESolver` execution
and are still exercised by direct low-level process tests.

Risk: Future high-level configured workflows could accidentally route native
`Process` objects through `Reaction`/`SimulationEngine` if these adapters are
treated as a main execution path instead of compatibility surface.

Exit condition: P1.4 proves each adapter is either unused by supported public
workflows and removes it, or explicitly isolates the adapter as legacy support
for a documented low-level purpose.

Removal milestone: Phase 1 Task 4, legacy adapter retirement.

Tests protecting it: `tests/test_guardrails_native_execution.py` runs supported
configured well-mixed configs with tripwires on `SimulationEngine`,
`Reaction`, and every current concrete `as_reaction()` method. Direct
low-level tests such as `tests/test_homogeneous_processes.py` and
`tests/test_generic_surface_processes.py` still document the active adapter
surface until P1.4 makes a final removal or containment decision.

## FD-005 Remaining Pyright optional-value baseline

Status: active

Reason: Pyright now checks invalid type forms, return types, assignment types,
argument types, attribute access, call issues, operator issues, optional
operands, and general type issues. Optional member access remains disabled
because calibration, transport, uncertainty, and plugin substrate modules still
need explicit non-null quantity narrowing.

Risk: Type checking can pass while some optional quantity/member access issues
remain in scientific modules. This must not be mistaken for a strict typing
guarantee.

Exit condition: optional-state contracts are rewritten or annotated so
`reportOptionalMemberAccess` can be re-enabled while remaining green in CI.

Removal milestone: the next optional-quantity narrowing package-quality ratchet.

Tests protecting it: `tests/test_quality_config.py` verifies that Pyright is a
declared dev dependency, that `pyrightconfig.json` exists, that stricter
diagnostics are enabled, and that CI runs the Pyright command. GitHub Actions
runs Pyright on every push and pull request.
