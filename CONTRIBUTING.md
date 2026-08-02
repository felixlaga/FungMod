# Contributing to FungMod

Thanks for your interest in improving FungMod. This document explains how to set
up a development environment, the standards your contribution must meet, and how
to submit changes. By participating you agree to abide by our
[Code of Conduct](CODE_OF_CONDUCT.md).

FungMod is a **scientific** project. Contributions that add or change science are
held to the integrity rules in [`AGENTS.md`](AGENTS.md): mechanisms must be
explicitly implemented, provenance-backed, maturity-labelled, tested, and honest
about assumptions and limitations. Software verification is never presented as
empirical validation. Please read `AGENTS.md` before proposing scientific
changes.

## Ways to contribute

- **Report bugs and unexpected results** via the
  [issue chooser](https://github.com/felixlaga/FungMod/issues/new/choose).
- **Ask usage questions** in
  [Discussions](https://github.com/felixlaga/FungMod/discussions) (see
  [SUPPORT.md](SUPPORT.md)).
- **Improve documentation**, including the
  [scientific user guide](docs/user-guide.md).
- **Add mechanisms, parameters, or datasets** following the provenance and
  maturity rules described below.
- **Fix bugs or improve performance** in the core engine.

## Development setup

FungMod supports Python 3.11–3.13. Clone the repository and install an editable
checkout with all optional dependency groups:

```bash
git clone https://github.com/felixlaga/FungMod.git
cd FungMod
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev,docs,notebooks]"
```

If you prefer an exactly pinned environment, install from the lock file (see
[Reproducibility](#reproducibility)):

```bash
python -m pip install -r requirements-lock.txt
python -m pip install -e ".[dev,docs,notebooks]" --no-deps
```

A container is also available:

```bash
docker build -t fungmod .
docker run --rm fungmod python -c "import fungmod; print(fungmod.__version__)"
```

## Quality gates

All of the following must pass before a pull request can be merged. They are run
in CI across the supported Python versions and operating systems, but please run
them locally first:

```bash
python -m ruff check src tests
python -m pyright --pythonpath "$(python -c 'import sys; print(sys.executable)')"
python -m pytest --cov=fungal_model --cov-report=term-missing --cov-report=xml
python -m mkdocs build --strict
python -m build
python -m twine check dist/*
```

You can run all of them at once with:

```bash
make check          # lint + type-check + tests + docs + package checks
```

- **Coverage** must stay at or above the 80% gate.
- **Docs** must build with `--strict` (no warnings).
- **Type checking** must pass; narrow nullable scientific values explicitly
  rather than suppressing diagnostics.

## Scientific-contribution rules

When a change touches mechanisms, parameters, registries, datasets, public API,
output schemas, or documented contracts:

1. **Provenance.** Every parameter used in a scientific simulation needs a
   traceable source. Do not introduce silent fallback constants. Unknown values
   must remain explicit or require an explicit exploratory opt-in.
2. **Maturity labelling.** Label new capability using the vocabulary in the
   [docs](https://fungmod.readthedocs.io/) (`implemented`,
   `technically verified`, `exploratory`, `scientifically validated`,
   `unsupported`).
3. **Genericity.** No substrate-, enzyme-, fungus-, or mechanism-specific
   branches in generic/core modules. A feature is not "generic" without a
   materially different non-specific test case.
4. **Tests.** Add or update tests whenever a guardrail, behaviour, public API,
   output schema, or documented contract changes.
5. **No hidden logic in notebooks.** Scientific logic lives in the package, not
   in notebooks.

## Submitting changes

1. Fork the repository and create a topic branch from `main`.
2. Make focused commits with clear messages.
3. Ensure all quality gates pass locally.
4. Open a pull request using the
   [pull request template](.github/pull_request_template.md). Describe what
   changed, what did not change, tests added or modified, scientific-behaviour
   impact, and backward-compatibility impact.
5. A maintainer will review. CI must be green and the branch up to date with
   `main` before merge. Branch-protection expectations are documented in
   [`.github/BRANCH_PROTECTION.md`](.github/BRANCH_PROTECTION.md).

## Documentation and Read the Docs

Documentation is built with MkDocs + Material and published on Read the Docs.
Build locally with `python -m mkdocs serve`. The published site is configured by
[`.readthedocs.yaml`](.readthedocs.yaml). Maintainers connecting the project for
the first time should import the repository at
<https://readthedocs.org/dashboard/import/> and point it at this repository; the
in-repo `.readthedocs.yaml` handles the rest.

## Releasing (maintainers)

1. Update the version in `pyproject.toml` and `CHANGELOG.md`.
2. Update `CITATION.cff` (`version` and `date-released`) and `codemeta.json`.
3. Tag the release `vX.Y.Z` and push the tag. The
   [release workflow](.github/workflows/release.yml) builds, checks, and
   publishes to PyPI via trusted publishing.
4. Zenodo archives the tagged release and mints a version DOI (see
   [`docs/user-guide.md`](docs/user-guide.md) and `.zenodo.json`). Update the
   concept DOI badge if this is the first archived release.

## License

By contributing, you agree that your contributions will be licensed under the
[MIT License](LICENSE) that covers the project.
