# Foundation Readiness Review

Date: 2026-05-28

This review is a software-foundation gate. It does not approve adding real
fungal biology, PETase mechanisms, literature parameters, metabolism, or
substrate-specific pathways.

## Current Result

The generic foundation path is operational for the required benchmark scope:

- homogeneous toy benchmark;
- explicit PET plugin benchmark;
- dummy non-PET surface benchmark.

All three run through `run_configured_model`, assemble through process
factories, execute through `AssembledModel.run()`, return `SimulationResult`,
validate, and save configured output bundles.

## Guardrails

- PET-specific execution remains outside generic workflow modules.
- Generic loaders use registries.
- State names, product maps, validators, and outputs are config-driven.
- High-level workflows do not construct low-level solvers directly.
- Notebooks import package code and exercise the generic workflow.
- CI runs Ruff, Pyright, and coverage-backed pytest.
- Coverage has an 80% minimum gate for the package.

## Active Architecture Debt

- `FD-005`: the Pyright gate is intentionally permissive around Pint quantity
  typing and optional-state inference.

This is a package-quality debt, not biology permission. The next quality ratchet
should tighten quantity typing before any real scientific mechanism work.

## Deferred

- real PETase kinetics;
- real fungal growth physiology;
- cellulose, lignin, chitin, or starch degradation mechanisms;
- intracellular metabolism;
- literature calibration;
- scientific parameter sets.

## Review Commands

```bash
python -m ruff check src tests
python -m pyright --pythonpath "$(python -c 'import sys; print(sys.executable)')"
python -m pytest tests/test_guardrails_config_generality.py tests/test_guardrails_native_execution.py
python -m pytest --cov=fungal_model --cov-report=term-missing --cov-report=xml
```
