# Changelog

All notable public releases of FungMod are documented here.

## [Unreleased]

## [0.1.1] — 2026-08-01

### Added

- Packaged, provenance-labelled parameter input for five purified fungal
  beta-glucosidases reported on cellobiose at matched assay conditions.
- A deterministic full notebook with configured dynamic glucose inhibition,
  2:1 glucose stoichiometry, inhibition-free counterfactuals, scenario
  summaries, figures, validators, diagnostics, and manifests.

### Scientific scope

- The new cases model purified enzymes labelled by fungal source, not
  whole-fungus physiology.
- Literature parameters remain separate from the explicit 10 nM showcase dose
  and starting-concentration assumptions.
- Transglycosylation, parameter uncertainty, empirical time-course validation,
  model discrepancy, and organism ranking remain unavailable.

## [0.1.0] — 2026-07-30

### Added

- PyPI distribution name `fungmod` with Python 3.11–3.13 metadata.
- `fungmod` convenience import namespace while retaining `fungal_model`.
- Immutable wheel-packaged registry, frozen source evidence, and example data.
- Public `default_registry_path()`, `example_data_path()`, and
  `package_data_path()` helpers.
- Installed-wheel fallback for the default virtual-experiment registry,
  frozen SABIO-RK Reaction 618 source proposal, configured example paths, and
  PET plugin benchmark assets.
- Artificial, framework-labelled dynamic-thermodynamics showcase configuration.
- Full zero-to-report and advanced-capabilities notebooks.
- MkDocs Material documentation configured for Read the Docs.
- Deterministic notebook/resource drift checks and isolated-wheel smoke tests.
- Trusted Publishing release workflow and expanded CI release gates.

### Scientific scope

- No new organism-specific biology or empirical validation data were added.
- The advanced inhibition and thermodynamic examples are artificial software
  benchmarks with explicit provenance, maturity, assumptions, and limitations.
- Existing exploratory ranges remain exploratory; they were not reclassified
  as calibration or validation evidence.

[Unreleased]: https://github.com/felixlaga/FungMod/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/felixlaga/FungMod/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/felixlaga/FungMod/releases/tag/v0.1.0
