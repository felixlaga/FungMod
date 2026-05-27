# Architecture Debt Register

This file is a containment mechanism, not permission to take shortcuts.

Temporary compromises are allowed only when they are documented here with an
ID, status, reason, risk, exit condition, removal milestone, and tests
protecting the boundary. New foundation work should remove entries from this
file, not normalize them.

## FD-001 Legacy PET workflow in the generic workflow package

Status: active transitional debt

Reason: `src/fungal_model/workflows/pet_surface_integration.py` predates the
generic configured-model workflow and is still needed by existing integration
tests. It is no longer exported from top-level `fungal_model`, but remains
available from `fungal_model.workflows` for compatibility.

Risk: PET remains visible from the generic workflow namespace and can keep
pulling high-level execution toward a substrate-specific path.

Exit condition: migrate the PET example to delegate through
`run_configured_model` or move the PET-specific workflow behind a
plugin/example boundary.

Removal milestone: full removal or plugin relocation by Milestone 8.

Tests protecting it: `tests/test_guardrails_no_hardcoding.py` permits only the
current exact legacy lines and fails on new PET-specific lines in generic
workflow paths.

## FD-002 PET-only substrate branch in YAML loading

Status: active transitional debt

Reason: `src/fungal_model/io/yaml_loader.py` currently has a PET-only
`load_substrate` implementation used by existing config and workflow tests.

Risk: generic entity loading can stay hardcoded to one substrate and block
non-PET foundation benchmarks.

Exit condition: replace `load_substrate` with a substrate loader registry that
supports PET plugin/example loading and at least one generic non-PET benchmark
substrate without a PET branch.

Removal milestone: Milestone 3.

Tests protecting it: `tests/test_guardrails_no_hardcoding.py` permits only the
current exact legacy lines and fails on new PET-specific lines in generic IO
paths.

## FD-003 `AssembledModel.run()` is not native execution yet

Status: active transitional debt

Reason: `AssembledModel.run()` exists as a public method but still raises
`NotImplementedError` until the process-centered ODE solver is introduced.

Risk: high-level workflows may continue manually constructing lower-level
solvers instead of routing through the assembled model.

Exit condition: implement solver-backed native execution on `AssembledModel.run`
that returns `fungal_model.results.SimulationResult`.

Removal milestone: Milestone 7.

Tests protecting it: `tests/test_guardrails_no_shortcuts.py` makes this the
only non-abstract public `NotImplementedError` allowance in high-risk source
paths, and `tests/test_guardrails_public_api.py` requires generic public API
names without faking end-to-end execution.

## FD-004 Configured-model runner is a structural preflight boundary

Status: active transitional debt

Reason: Milestone 2 introduces `run_configured_model` as the generic public
entry point before registry-based entity loading, process factories, native
assembled-model execution, and configured output bundles exist.

Risk: users can see the correct generic entry point before it can execute a
model end to end.

Exit condition: `run_configured_model` loads entities through registries,
builds processes through factories, assembles a model, calls
`AssembledModel.run()`, validates the result, and saves the output bundle.

Removal milestone: Milestone 8.

Tests protecting it: `tests/test_guardrails_public_api.py` requires the public
API names to exist and checks that `run_configured_model` fails with a
structured report rather than silently constructing a substrate-specific path.
