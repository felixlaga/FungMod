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
| Configured calibration against synthetic and literature datasets | Implemented | Toy, framework, calibrated, and validated dataset maturities fail closed. Fitting a published dataset is parameter estimation; a literature fit carries its own non-validation assumptions and warnings. |
| Calibration evidence audit | Implemented | A pass means declared software criteria passed; publication authorization is always false. |
| Synthetic-data utilities | Implemented for software tests | Synthetic data must never be presented as scientific evidence. |
| First literature time-course comparison | Implemented for one same-source no-refit consistency check | The nine digitized observations and source-model parameters are not independent validation; digitization resolution is not experimental uncertainty. |
| Held-out condition study across all four Figure S1 series | Implemented for one publication | Four series, 36 digitized observations, from one figure by one laboratory. Held-out agreement shows transfer across experimental conditions, not independent replication. |
| Three independent literature sources, five series, four enzyme preparations | Implemented | Alvarez-Gonzalez 2022 (60 min), Ariaeenejad 2020 (380 h), Cao 2015 (10 h). Only the first carries a held-out condition; for the other two the cross-source test is structural adequacy under fitting, not predictive validation. |
| Cross-source structural adequacy test with identifiability screening | Implemented | Flags bound-pinned parameters and ill-conditioned Jacobians, so a low RMSE reached by parameter compensation is not reported as success. One of five series is flagged degenerate. |
| Monte Carlo, local, and global sensitivity | Implemented | Global indices assume independent explicit input distributions; no empirical biological distribution is supplied. |

## Not currently supported

- complete arbitrary fungus/substrate/environment prediction;
- resolved whole-fungus secretion, uptake, regulation, transporters, toxicity,
  respiration, and intracellular metabolism;
- publication-grade calibration and broad external validation;
- predictive validation on the second and third literature sources. Each of
  those provides a single condition per enzyme, so the model can be fitted to
  them but not tested out-of-sample against them. Only Alvarez-Gonzalez 2022
  supplies a genuine held-out condition;
- any reconciliation of the fitted PersiBGL1 product-inhibition constant
  (about 34 mM) with that source's own claim of a glucose inhibition constant
  near 8.8 M. The fit reproduces the observed plateau by strong product
  inhibition, which contradicts the source's glucose-tolerance claim. The
  discrepancy is recorded and unexplained;
- transfer of homogeneous Michaelis-Menten parameters across enzyme loading. In
  the one condition tested, a nominal five-fold increase in free beta-glucosidase
  raised the observed initial rate only about 1.6-fold, an apparent scaling of
  `[E]^0.28` rather than the linear `V_max = k_cat * [E]` the configured model
  assumes. Refitting does not remove the discrepancy, so it is a structural gap
  and not a parameter-estimation problem. Two candidate mechanisms were tested
  and both failed, so neither is implemented
  (`scripts/run_alvarez_gonzalez_2022_mechanism_hypotheses.py`):
  first-order thermal deactivation is falsified, since the fitted half-life of
  about 1189 min is negligible against a 60 min assay and every held-out
  condition degrades; and a single sub-linear enzyme-scaling exponent is not
  supported, since the two affected series imply exponents of 0.55 and 0.79 and
  cross-prediction between them fails in one direction. Because the same figure
  also prints inconsistent enzyme-concentration units, the panel-B enzyme
  metadata is treated as insufficiently reliable for model comparison and those
  series are excluded from validation claims;
- coupled-network thermodynamic flux optimization;
- state-dependent electrolyte/activity-coefficient models;
- correlated-input global sensitivity and Bayesian calibration;
- irregular spatial models and dynamic morphology;
- resolved PET MHET/BHET/TPA/EG product chemistry;
- validated default models for lignin, starch, chitin, or full
  lignocellulose.

Unsupported scope should remain explicit in preflight, limitations, or errors.
