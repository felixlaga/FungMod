# Phase 1 Legacy Adapter Retirement

Date: 2026-06-14

Plan scope: P1.4 from `FUNGMOD_PHASE_1_REPOSITORY_TRUTH_AND_EXECUTION_HARDENING.md`.

Review anchor: current working tree after P1.3 native execution verification.

This pass retires process-to-`Reaction` compatibility adapters only. It does
not remove the low-level `Reaction` or `SimulationEngine` APIs and does not
change scientific models, parameters, numerical methods, public configured
workflow semantics, or result outputs.

## Adapter Retirement Matrix

| Adapter | Previous location | Supported production workflow use | Previous test use | P1.4 action | Evidence |
|---|---|---|---|---|---|
| `_reaction_from_process(...)` | `src/fungal_model/processes/homogeneous.py` | None found | Helper used only by homogeneous `as_reaction()` methods | Removed | `rg` found no production call sites outside the removed adapters |
| `FirstOrderDecayProcess.as_reaction()` | `src/fungal_model/processes/homogeneous.py` | None found | `tests/test_homogeneous_processes.py` used it to run a process through `SimulationEngine` | Removed; test now runs through `ModelBuilder` and native `AssembledModel.run()` | `tests/test_homogeneous_processes.py`; `tests/test_guardrails_native_execution.py` |
| `MassActionProcess.as_reaction()` | `src/fungal_model/processes/homogeneous.py` | None found | No direct test call found in current tree | Removed | `rg -n "as_reaction\\(" src tests notebooks` |
| `HomogeneousMichaelisMentenProcess.as_reaction()` | `src/fungal_model/processes/homogeneous.py` | None found | No direct test call found in current tree | Removed | `rg -n "as_reaction\\(" src tests notebooks` |
| `SurfaceCatalysisProcess.as_reaction()` | `src/fungal_model/processes/surface.py` | None found | `tests/test_generic_surface_processes.py` used it to run a process through `SimulationEngine` | Removed; test now runs through `ModelBuilder` and native `AssembledModel.run()` | `tests/test_generic_surface_processes.py`; `tests/test_guardrails_native_execution.py` |

## Supported Workflow Check

Supported configured workflows already executed through:

`run_configured_model` -> `ConfiguredModelRunner.run` -> `AssembledModel.run` -> `ProcessODESolver.run`

P1.4 kept and extended the P1.3 guardrails:

- supported configured well-mixed benchmarks fail if they instantiate
  `SimulationEngine` or construct legacy `Reaction` objects;
- configured unsupported `film_1d` geometry still fails explicitly through
  `ProcessODESolver`;
- high-level workflows, PET plugin helpers, and supported example notebooks
  are scanned for direct low-level solver shortcuts;
- process modules are scanned so `def as_reaction` and
  `_reaction_from_process` cannot silently return.

## Retained Legacy APIs

The following low-level APIs remain intentionally supported:

- `fungal_model.chemistry.reactions.Reaction`;
- `fungal_model.core.simulation.SimulationEngine`;
- `fungal_model.transport.reaction_diffusion.ReactionDiffusionEngine1D`.

They are retained as direct low-level APIs. They are no longer reachable from
generic configured process execution through process-to-`Reaction` adapters.

## Numerical Behavior

No configured workflow, process rate law, contribution equation, solver
setting, parameter, unit conversion, validator, output schema, or public
configured entry point changed. Tests that previously used adapters now verify
the same process behavior through native process execution. Direct
reaction-engine tests construct `Reaction` objects explicitly.

## Exit Decision

`FD-006` is resolved. No process-to-`Reaction` compatibility adapter remains in
production process modules. Future spatial or low-level reaction workflows must
use explicit low-level APIs or add a documented, tested solver route rather than
reintroducing a generic process adapter bridge.
