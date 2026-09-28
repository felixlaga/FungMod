# Release notes

## Unreleased

- Fixed mixed-unit SBML trajectories, preserved PEtab training/validation/holdout separation, and rejected missing or zero export noise scales. Packaged PEtab examples resolve outside the checkout. Regenerate older affected exports.
- Fixed thermodynamic scalar typing and pinned the checked Pyright version for local/CI parity.
- Consolidated exploratory inhibition runners through shared unit-aware package integration and the configured inhibition kernel (FD-008 resolved).
- Added explicit-noise grid profile likelihood and checksum-bound frozen-prediction evaluation with raw replicate evidence. Independent empirical validation remains pending on suitable external data.
- Corrected configured calibration when uncertainty units differ from observation units.

- Corrected comparison degrees of freedom and preserved pointwise calibration
  uncertainty. Reduced chi-square now requires explicit `fitted_parameter_count`.
- Removed a pNPG-to-cellobiose parameter substitution, added research-runner
  convergence and reference-trajectory checks, and replaced automatic mechanism
  verdicts with descriptive results. Research summaries use schema `2.0.0`;
  regenerate earlier output folders. Independent biological validation remains
  pending.

## 0.1.1 — 2026-08-01

- Added a packaged literature-transcribed showcase input and a full notebook
  for five purified fungal beta-glucosidases acting on cellobiose.
- The notebook uses one generic configured mechanism, dynamic glucose
  inhibition, explicit 2:1 glucose stoichiometry, paired no-inhibition
  counterfactuals, standard output bundles, and a cross-case manifest.
- The source-organism labels are not whole-fungus models. Parameter uncertainty
  remains unknown, the standardized dose is an explicit scenario assumption,
  and empirical validation and organism ranking remain unavailable.
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
