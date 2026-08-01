# Capability map

This page separates implemented software from scientific maturity.

## Researcher-facing workflow

| Capability | Status | Boundary |
| --- | --- | --- |
| Registry-backed virtual experiments | Implemented and technically verified | Registry coverage is scoped, not a complete biological database. |
| Researcher-facing aliases | Implemented | Ambiguous and unknown names fail explicitly. |
| Environment grids | Implemented | Values affect rates only through explicit laws or condition-specific records. |
| Exploratory ensembles | Implemented | Quantiles are conditional on explicit ranges, not calibrated posteriors. |
| Scientific-mode exact-input gate | Implemented | Exact-input eligibility is not empirical validation. |
| Standard tables, plots, reports, manifests | Implemented | Presentation is derived from existing output rows. |
| Suggested-experiment output | Implemented for scoped cases | Suggestions do not claim that an experiment has been performed. |

## Mechanisms and numerical models

| Capability | Status | Boundary |
| --- | --- | --- |
| Well-mixed process ODEs | Implemented | Unsupported geometry fails before execution. |
| First-order, mass-action, homogeneous Michaelis-Menten | Implemented | Homogeneous Michaelis-Menten is dissolved-substrate kinetics. |
| Surface adsorption/catalysis | Implemented, generic framework | Substrate-specific accessibility and morphology remain scoped. |
| Linear, branching, and cyclic enzyme pathways | Implemented and software-verified | Broad provenance-backed pathway biology remains partial. |
| Temperature, pH, oxygen, water-activity modifiers | Implemented when explicitly configured | No response is inferred from metadata alone. |
| Reversible product inhibition | Implemented for explicit matched inputs | No toxicity, uptake, or whole-fungus inference. |
| Competitive and Haldane substrate inhibition | Implemented with provenance/maturity contracts | Framework values are artificial; the five-enzyme showcase uses separately labelled literature-reported inputs but remains unvalidated. |
| Coupled hydrolysis and substrate transglycosylation | Implemented as a generic process law with one provenance-backed fungal-enzyme configuration | The transfer-product pool is unresolved; no product-linkage assignment, re-hydrolysis, or whole-fungus claim is made. |
| Minimal well-mixed fungal process coupling | Implemented and software-tested | Caller-supplied degradation, capability, assimilation, secretion, uptake, yield, and maintenance inputs remain exploratory; no organism-specific physiology or validation is bundled. |
| Dynamic single-process thermodynamic constraints | Implemented | Configured enforcement remains ideal-dilute and forward-rate blocking. |
| Constant-coefficient nonideal reversible thermodynamics | Implemented as a separate low-level API | Coefficients and the forward kinetic scale must be sourced; no electrolyte model or configured assembly is inferred. |
| 1D and uniform Cartesian 2D/3D reaction diffusion | Implemented and software-tested | No irregular mesh, porous morphology, moving boundary, or empirical spatial validation. |

## Data, curation, and validation

| Capability | Status | Boundary |
| --- | --- | --- |
| Offline-first SABIO-RK proposals | Implemented | Proposals are review-only and never mutate the registry. |
| Curator decision bundles and signatures | Implemented | Acceptance is not scientific validation or simulation authorization. |
| Transactional registry promotion | Implemented | Promotion requires exact reviewed bytes and explicit writable targets. |
| Generic least-squares calibration utilities | Implemented | No parameters are calibrated by default. |
| Calibration evidence audit | Implemented | A pass means declared software criteria passed; publication authorization is always false. |
| Synthetic-data utilities | Implemented for software tests | Synthetic data must never be presented as scientific evidence. |
| First literature time-course comparison | Implemented for one same-source no-refit consistency check | The nine digitized observations and source-model parameters are not independent validation; digitization resolution is not experimental uncertainty. |
| Monte Carlo, local, and global sensitivity | Implemented | Global indices assume independent explicit input distributions; no empirical biological distribution is supplied. |

## Not currently supported

- complete arbitrary fungus/substrate/environment prediction;
- resolved whole-fungus secretion, uptake, regulation, transporters, toxicity,
  respiration, and intracellular metabolism;
- publication-grade calibration and broad external validation;
- coupled-network thermodynamic flux optimization;
- state-dependent electrolyte/activity-coefficient models;
- correlated-input global sensitivity and Bayesian calibration;
- irregular spatial models and dynamic morphology;
- resolved PET MHET/BHET/TPA/EG product chemistry;
- validated default models for lignin, starch, chitin, or full
  lignocellulose.

Unsupported scope should remain explicit in preflight, limitations, or errors.
