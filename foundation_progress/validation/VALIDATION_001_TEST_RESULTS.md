# VALIDATION-001 Test Results

Date: 2026-06-07

Scope: validation-only. No source-code fixes were applied. Commands were run from `/Users/felix/Documents/GitHub/FungMod`.

## Environment

- Platform reported by pytest: `darwin`
- Python reported by pytest: `3.13.11`
- Pytest reported by pytest: `9.0.3`
- Pluggy reported by pytest: `1.6.0`
- Pytest plugins reported: `cov-7.1.0`, `anyio-4.13.0`
- Command prefix used for pytest/quality checks: `env MPLCONFIGDIR=/private/tmp/fungmod-mpl .venv/bin/python -m ...`

## Required Targeted Tests

### `pytest tests/test_sabiork_reaction_618_registry_case.py`

Command:

```bash
env MPLCONFIGDIR=/private/tmp/fungmod-mpl .venv/bin/python -m pytest tests/test_sabiork_reaction_618_registry_case.py
```

Result:

```text
collected 16 items
tests/test_sabiork_reaction_618_registry_case.py ................ [100%]
16 passed in 1.62s
```

### `pytest tests/test_registry_ensemble_homogeneous_mm.py`

Command:

```bash
env MPLCONFIGDIR=/private/tmp/fungmod-mpl .venv/bin/python -m pytest tests/test_registry_ensemble_homogeneous_mm.py
```

Result:

```text
collected 3 items
tests/test_registry_ensemble_homogeneous_mm.py ... [100%]
3 passed in 8.47s
```

### `pytest tests/test_registry_ensemble_simulation.py`

Command:

```bash
env MPLCONFIGDIR=/private/tmp/fungmod-mpl .venv/bin/python -m pytest tests/test_registry_ensemble_simulation.py
```

Result:

```text
collected 6 items
tests/test_registry_ensemble_simulation.py ...... [100%]
6 passed in 3.98s
```

### `pytest tests/test_environment_grid.py`

Command:

```bash
env MPLCONFIGDIR=/private/tmp/fungmod-mpl .venv/bin/python -m pytest tests/test_environment_grid.py
```

Result:

```text
collected 3 items
tests/test_environment_grid.py ... [100%]
3 passed in 0.59s
```

### `pytest tests/test_virtual_experiment_environment_grid.py`

Command:

```bash
env MPLCONFIGDIR=/private/tmp/fungmod-mpl .venv/bin/python -m pytest tests/test_virtual_experiment_environment_grid.py
```

Result:

```text
collected 2 items
tests/test_virtual_experiment_environment_grid.py .. [100%]
2 passed in 2.15s
```

### `pytest tests/test_sabiork_reaction_618_parameter_ranges.py`

Command:

```bash
env MPLCONFIGDIR=/private/tmp/fungmod-mpl .venv/bin/python -m pytest tests/test_sabiork_reaction_618_parameter_ranges.py
```

Result:

```text
collected 6 items
tests/test_sabiork_reaction_618_parameter_ranges.py ...... [100%]
6 passed in 0.51s
```

### `pytest tests/test_bio001_surface_cellulose_virtual_experiment.py`

Command:

```bash
env MPLCONFIGDIR=/private/tmp/fungmod-mpl .venv/bin/python -m pytest tests/test_bio001_surface_cellulose_virtual_experiment.py
```

Result:

```text
collected 3 items
tests/test_bio001_surface_cellulose_virtual_experiment.py ... [100%]
3 passed in 1.33s
```

## Additional Targeted Tests

These were added because they directly exercise the public virtual-experiment API and notebooks.

Command:

```bash
env MPLCONFIGDIR=/private/tmp/fungmod-mpl .venv/bin/python -m pytest tests/test_virtual_experiment_api.py tests/test_sabiork_reaction_618_notebook.py tests/test_bio001_notebook.py tests/test_notebooks.py
```

Result:

```text
collected 16 items
tests/test_virtual_experiment_api.py ..... [ 31%]
tests/test_sabiork_reaction_618_notebook.py .... [ 56%]
tests/test_bio001_notebook.py ... [ 75%]
tests/test_notebooks.py .... [100%]
16 passed in 9.80s
```

## Full Test Suite

Command:

```bash
env MPLCONFIGDIR=/private/tmp/fungmod-mpl .venv/bin/python -m pytest
```

Result:

```text
collected 450 items
450 passed in 30.20s
```

Important interpretation: this is strong software evidence for the current contracts, but it is not scientific validation of Reaction 618 predictions, environment effects, or BIO-001 cellulose degradation.

## Quality Checks

### Ruff Over Entire Repository

Command:

```bash
env MPLCONFIGDIR=/private/tmp/fungmod-mpl .venv/bin/python -m ruff check .
```

Result: failed with 9 notebook `E402` import-position errors.

Exact failure summary:

```text
Found 9 errors.
```

Affected notebook cells:

- `notebooks/06_sabiork_reaction_618_beta_glucosidase.ipynb`: 3 `E402` errors.
- `notebooks/07_bio001_cellulose_surface_virtual_experiment.ipynb`: 2 `E402` errors.
- `notebooks/examples/00_quickstart.ipynb`: 1 `E402` error.
- `notebooks/examples/01_config_entity_inspection.ipynb`: 1 `E402` error.
- `notebooks/examples/02_failure_report.ipynb`: 1 `E402` error.
- `notebooks/examples/03_configured_outputs.ipynb`: 1 `E402` error.

Interpretation: the configured project quality gate does not appear to be `ruff check .`; it is `ruff check src tests`. The repository should decide whether notebooks are linted, exempted, or normalized.

### Ruff Source And Tests Gate

Command:

```bash
env MPLCONFIGDIR=/private/tmp/fungmod-mpl .venv/bin/python -m ruff check src tests
```

Result:

```text
All checks passed!
```

### Pyright

Command:

```bash
env MPLCONFIGDIR=/private/tmp/fungmod-mpl .venv/bin/python -m pyright --pythonpath .venv/bin/python
```

Result:

```text
0 errors, 0 warnings, 0 informations
```

### Diff Whitespace Check

Command:

```bash
git diff --check
```

Result: passed with no output.

### Tracked Worktree State

Command:

```bash
git status --short
```

Result: clean tracked worktree after validation commands and before report writing.

Note: `.coverage` and `coverage.xml` are present as ignored files. The coverage command was not run during this pass because it would update non-validation artifacts outside `foundation_progress/validation/`.

