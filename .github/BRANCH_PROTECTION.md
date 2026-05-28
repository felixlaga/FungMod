# Branch Protection Expectations

Configure the default branch in GitHub to require the `CI / tests` workflow
before merge.

The CI workflow currently blocks on:

- `python -m ruff check src tests`
- `python -m pyright --pythonpath "$(python -c 'import sys; print(sys.executable)')"`
- `python -m pytest --cov=fungal_model --cov-report=term-missing --cov-report=xml`

Coverage must stay at or above the `fail_under` threshold configured in
`pyproject.toml`.

This file documents repository policy. The actual branch protection rule must
be enabled in the GitHub repository settings by a maintainer with permission.

The current Pyright baseline is intentionally permissive around Pint quantity
typing. Tightening those diagnostics is a future package-quality milestone after
the quantity aliases and optional-state contracts are made Pyright-clean.
