# Architecture Debt Register

This file is a containment mechanism, not permission to take shortcuts.

Temporary compromises are allowed only when they are documented here with an
ID, status, reason, risk, exit condition, removal milestone, and tests
protecting the boundary. New foundation work should remove entries from this
file, not normalize them.

## FD-001 Legacy PET workflow in the generic workflow package

Status: active transitional debt

Reason: `src/fungal_model/workflows/pet_surface_integration.py` and
`src/fungal_model/workflows/__init__.py` predate the generic configured-model
workflow and are still needed by existing integration tests.

Risk: PET remains visible from the generic workflow namespace and can keep
pulling high-level execution toward a substrate-specific path.

Exit condition: introduce `run_configured_model` and migrate the PET example to
delegate through it or move the PET-specific workflow behind a plugin/example
boundary.

Removal milestone: Milestone 2 for generic-first public API deprecation, with
full removal or plugin relocation by Milestone 8.

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
paths, and `tests/test_guardrails_public_api.py` marks the next generic public
API names without faking them.
