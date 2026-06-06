# Notebooks, Documentation, CI, and Package Quality Plan

## Objective

Reach serious scientific Python package maturity before adding biology.

## Notebooks

Notebooks demonstrate; they do not implement.

Foundation notebooks:

```text
00_quickstart_configured_model.ipynb
01_model_config_and_entities.ipynb
02_process_library_and_factory_demo.ipynb
03_native_assembled_model_run.ipynb
04_failure_modes_and_reports.ipynb
05_outputs_and_validation.ipynb
06_backend_and_solver_benchmark.ipynb
```

Tests: notebooks exist, import `fungal_model`, do not define core classes, quickstart executes.

## Docs

Create docs for installation, quickstart, architecture, model configs, entities, process factories, assembled model, solvers, results, validation, guardrails, contributing.

## CI

Required first: pytest and architecture guardrails.

Then add: ruff, pyright, coverage, notebook smoke tests.

## pyproject dev tools

Add dev dependencies gradually:

```toml
pytest
pytest-cov
ruff
pyright
nbformat
```

## Branch protection

Protect `main`. Require PR, CI pass, up-to-date branch, no force pushes.

## README quality

Only show real badges for systems that exist. No fake coverage or type-check badges.

## Done when

1. CI passes on every PR;
2. guardrail tests run in CI;
3. notebooks demonstrate generic APIs;
4. docs explain architecture;
5. README reflects reality;
6. ruff/pyright/coverage introduced;
7. branch protection active.
