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
| Dynamic single-process thermodynamic constraints | Implemented | Coupled-network optimization, reverse rates, and nonideal activities are unsupported. |
| 1D reaction diffusion | Implemented initial finite-volume engine | No 2D/3D or porous morphology model. |

## Data, curation, and validation

| Capability | Status | Boundary |
| --- | --- | --- |
| Offline-first SABIO-RK proposals | Implemented | Proposals are review-only and never mutate the registry. |
| Curator decision bundles and signatures | Implemented | Acceptance is not scientific validation or simulation authorization. |
| Transactional registry promotion | Implemented | Promotion requires exact reviewed bytes and explicit writable targets. |
| Generic least-squares calibration utilities | Implemented | No publication-grade biological calibration is bundled. |
| Synthetic-data utilities | Implemented for software tests | Synthetic data must never be presented as scientific evidence. |
| Literature validation datasets | Infrastructure implemented; publication-grade coverage unavailable | Missing real observations remain unavailable, never invented. |

## Not currently supported

- complete arbitrary fungus/substrate/environment prediction;
- resolved whole-fungus secretion, uptake, regulation, transporters, toxicity,
  respiration, and intracellular metabolism;
- publication-grade calibration and broad external validation;
- coupled-network thermodynamic flux optimization;
- nonideal activities and reverse-rate thermodynamics;
- global sensitivity and Bayesian calibration;
- 2D/3D spatial models and dynamic morphology;
- resolved PET MHET/BHET/TPA/EG product chemistry;
- validated default models for lignin, starch, chitin, or full
  lignocellulose.

Unsupported scope should remain explicit in preflight, limitations, or errors.
