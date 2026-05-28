# Branch Protection Expectations

Configure the default branch in GitHub so all changes must enter through pull
requests and the `CI / tests` workflow must pass before merge.

The CI workflow currently blocks on:

- `python -m ruff check src tests`
- `python -m pyright --pythonpath "$(python -c 'import sys; print(sys.executable)')"`
- `python -m pytest --cov=fungal_model --cov-report=term-missing --cov-report=xml`

Coverage must stay at or above the `fail_under` threshold configured in
`pyproject.toml`.

Required branch-protection settings:

- require pull requests before merging;
- require the `CI / tests` status check to pass before merging;
- require branches to be up to date before merging;
- block force pushes on the protected branch;
- block direct bypass of branch protection except for explicitly audited
  emergency administrators.

This file documents repository policy. The actual branch protection rule must
be enabled in the GitHub repository settings by a maintainer with permission.

The current Pyright baseline is intentionally permissive around Pint quantity
typing. Tightening those diagnostics is a future package-quality milestone after
the quantity aliases and optional-state contracts are made Pyright-clean.
