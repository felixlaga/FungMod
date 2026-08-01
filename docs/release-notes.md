# Release notes

## Unreleased

- Added one provenance-matched, no-refit comparison with nine digitized
  literature time-course observations; this is same-source consistency, not
  independent validation.
- Added a generic coupled hydrolysis/transglycosylation process and one
  provenance-backed *Phanerochaete chrysosporium* BGL1B configuration.
- Added a minimal exploratory well-mixed fungal-process coupling API, uniform
  Cartesian 2D/3D reaction diffusion, and constant-coefficient nonideal
  reversible thermodynamics.
- Added variance-based independent-input global sensitivity with Saltelli
  first-order and Jansen total-order estimators.
- Added a publication-oriented calibration evidence audit whose software pass
  never authorizes a publication claim.
- Removed the tracked package-resource mirror; source distributions now stage
  canonical data deterministically into wheels.

## 0.1.1 — 2026-08-01

- Added a packaged literature-transcribed showcase input and a full notebook
  for five purified fungal beta-glucosidases acting on cellobiose.
- The notebook uses one generic configured mechanism, dynamic glucose
  inhibition, explicit 2:1 glucose stoichiometry, paired no-inhibition
  counterfactuals, standard output bundles, and a cross-case manifest.
- The source-organism labels are not whole-fungus models. Parameter uncertainty
  remains unknown, the standardized dose is an explicit scenario assumption,
  and empirical validation and organism ranking remain unavailable.

## 0.1.0 — 2026-07-30

FungMod's first public alpha release packages the existing mechanistic
virtual-experiment engine for standard Python installation.

Highlights:

- `python -m pip install fungmod`;
- `import fungmod` convenience namespace plus backward-compatible
  `import fungal_model`;
- wheel-contained registry, frozen source evidence, and example
  configurations;
- complete standard virtual-experiment tables, quick-look plots, reports, and
  manifests;
- two end-to-end release notebooks;
- Read the Docs-ready MkDocs documentation;
- package, documentation, notebook, lint, type, and test gates;
- Trusted Publishing workflow for PyPI releases.

Scientific scope remains deliberately bounded. The release is alpha software,
not a blanket claim of empirical validation for fungus/substrate/environment
predictions.

See the repository [`CHANGELOG.md`](https://github.com/felixlaga/FungMod/blob/main/CHANGELOG.md)
for the distributable release record.
