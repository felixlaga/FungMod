# Capability map

This page separates implemented software from scientific maturity.

The [joint culture/activity benchmark](gelain-joint-benchmark.md) compares seven
model/family combinations against 144 published means. It includes assay-specific
observations, retained dry-mass hypotheses, explicit error assumptions and
model-bound validation contracts. Better retrospective prediction does not
resolve parameter identifiability or supply independent empirical evidence.

## Researcher-facing workflow

| Capability | Status | Boundary |
| --- | --- | --- |
| Registry-backed virtual experiments | Implemented and technically verified | Registry coverage is scoped, not a complete biological database. |
| Researcher-facing aliases | Implemented | Ambiguous and unknown names fail explicitly. |
| User-supplied enzyme and kinetics tables | Implemented (USERDATA-001 to USERDATA-010, ASSEMBLE-001) | `load_user_dataset` validates a manifest and CSV tables and `VirtualExperiment(user_data=...)` overlays the generated, namespaced records in memory. Dissolved substrates, or one suspended solid polymer on a dry-mass basis (USERDATA-008: the same law as an apparent bulk law in mass per volume with a g/g yield; the enzyme as a protein mass or an assay activity per volume, or as an `enzyme_dose` per substrate mass giving one derived record; `kcat` checked per case with pint; an optional `reactivity_exponent` binding the existing `(S/S0)^n` modifier with `S0` the case's own initial-substrate record; the activity routes to Vmax, the pH-ionization form, molar units, composite substrates and adsorption or surface-area inputs refused; no adsorption, synergy, product inhibition or LPMO kinetics; see [solid substrates](user-data.md#solid-substrates)), and Michaelis-Menten in the `kcat` form (with an enzyme concentration), the Vmax form, or the diprotic pH-ionization form (limiting turnover and Km, four pK values and the fitted pH range, bound to the `ph_ionization_michaelis_menten` process law so the rate follows the environment pH; condition pH must be exact and inside the fitted range, and a pH law on such a pair is refused), Vmax from one route per case (a `vmax` row, specific activity x enzyme loading as a derived record, or a saturating assay activity on the case substrate); optional `responses.csv` binds the cardinal temperature, cardinal pH or Arrhenius law through the template modifiers, with kinetic constants required at the law's reference condition. Optional `genomes.csv` resolves a strain's enzyme classes from a dbCAN annotation or a UniProtKB TSV export of its proteome (classes only, never rates). Optional `timecourse.csv` series can be compared with simulations and used to fit Km with kcat or Vmax (labelled `fitted`, exploratory only). Optional `culture.csv` (USERDATA-009) binds the registry's existing `culture_physiology` model (the *T. harzianum* P49P11 case's composition) to a user's strain growing on one solid substrate: substrate consumption by one secreted enzyme pool, biomass with an explicit yield and a closure ledger, first-order biomass loss, and substrate-induced synthesis and first-order loss of each pool (protein mass or assay units, never converted); every role is a record or a gap with a plain-words measurement request, units are checked with pint per role and per case, the weakest input sets the mode, and no new numerics are added; one fungus per case, no spatial mycelium, oxygen or pH dynamics, no response laws, time courses or assembly route for cultures, and cultures never mixed with the enzyme-assay forms for one strain and substrate (see [fungal culture](user-data.md#fungal-culture-growth-and-secretion)). An optional `enzyme_network` block in the manifest (USERDATA-010) makes every case an enzyme network: every declared class of the strain that acts on a pool runs its own homogeneous Michaelis-Menten process (kcat or Vmax form) through a new `enzyme_network` template type assembled by the existing composition builder, processes on one pool add their rates, a pool released by one class is the next class's substrate only where a substrate's `substrates.csv` product equals another `substrate_id`, and a `ki` row with an `inhibitor` binds the existing provenance-bound `competitive_inhibition` modifier (no inhibition term without one); cycles, ambiguous products, links across the dissolved and dry-mass bases, a class on two pools of one network, strains with different member classes, the pH-ionization form and response laws, cultures and time courses in a network are refused; no synergy, competition for substrate or adsorption sites, competing substrates of one enzyme or other inhibition forms (see [several enzymes acting together](user-data.md#several-enzymes-acting-together)). No promotion into the shared registry. Missing roles become explicit unknowns with measurement requests. `user_tables_from_sabiork` drafts the tables from SABIO-RK entries for review, and `assemble_user_tables` drafts one dataset for a fungus, substrates and conditions from its annotation, asserted classes, registry record, a user dataset and SABIO-RK entries, reporting per case whether the kinetics are the user's, same-species literature, a cross-organism transfer (an estimate), a conflict or a gap; kinetics are never reused at another condition except through a response law at an `EnvironmentGrid` condition. See [user-supplied data](user-data.md). |
| Environment grids | Implemented | Values affect rates only through explicit laws or condition-specific records; a bound law reports `active_response_model`, and ranking is allowed only when every condition that varies across the screen is covered. See [environment response laws](environment-response.md). |
| Exploratory ensembles | Implemented | Quantiles are conditional on explicit ranges, not calibrated posteriors. |
| Scientific-mode exact-input gate | Implemented | Exact-input eligibility is not empirical validation. |
| Standard tables, plots, reports, manifests | Implemented | Presentation is derived from existing output rows. |
| Suggested-experiment output | Implemented for scoped cases | Suggestions do not claim that an experiment has been performed. |

## Mechanisms and numerical models

| Capability | Status | Boundary |
| --- | --- | --- |
| Well-mixed process ODEs | Implemented; compiled numeric right-hand side | Units resolve at build time, stoichiometry is probed for linearity, every process's kernel kind is recorded; rates are evaluated at `max(state, 0)` so pools can deplete without clipping the trajectory; unsupported geometry fails before execution. See [compiled core](compiled-core.md). |
| Whole-organism registry case | Implemented; one organism, retrospectively calibrated | *T. harzianum* P49P11 on particulate cellulose runs in `scientific` mode through `VirtualExperiment` with biomass, two enzyme-activity pools, substrate and closure ledgers. Constants are a frozen retrospective fit to published means, not validated predictions; nutrient, oxygen and maintenance physiology are absent. See [organism physiology](organism-physiology.md). |
| Per-state numerical tolerances and sparse spatial Jacobians | Implemented across main engines and joint culture research API | Explicit units and complete state coverage; failed/incomplete runs reject; local numerical error control is not measurement uncertainty. See [audit](solver-thermodynamic-audit.md). |
| Coupled detailed-balance networks and free-energy equilibrium | Implemented and software-tested | Closed ideal-dilute fixed-volume isothermal elementary mass action; sourced formation energies and kinetics required. Zero-concentration entropy diagnostics are unavailable; no organism validation. |
| First-order, mass-action, homogeneous Michaelis-Menten | Implemented | Homogeneous Michaelis-Menten is dissolved-substrate kinetics. |
| Surface adsorption/catalysis | Implemented, generic framework | Substrate-specific accessibility and morphology remain scoped. |
| Linear, branching, and cyclic enzyme pathways | Implemented and software-verified | Broad provenance-backed pathway biology remains partial. |
| Temperature, pH, oxygen, water-activity modifiers | Implemented when explicitly configured | Arrhenius, Rosso cardinal temperature (CTMI), Gaussian pH, Rosso cardinal pH (CPM), Monod oxygen, water-activity threshold and the Rosso and Robinson cardinal water-activity law; no response is inferred from metadata alone, and the three cardinal laws are bound to no shipped organism because no sourced cardinal values exist in the repository. |
| pH-ionization Michaelis-Menten and thermal inactivation process laws | Implemented; one sourced pH-response case | Diprotic ionization pH dependence of `kcat` and `Km` (SABIO-RK law type 24) bound to *P. chrysosporium* BGL1A on cellobiose over pH 4 to 8 (Tsukada 2008 via SABIO-RK entry 38522), exploratory mode only because the assay loadings are explicit assumptions. First-order Arrhenius thermal inactivation is implemented and tested but bound to no shipped case (no sourced inactivation energy). See [environment response laws](environment-response.md). |
| Reversible product inhibition | Implemented for explicit matched inputs | No toxicity, uptake, or whole-fungus inference. |
| Competitive and Haldane substrate inhibition | Implemented with provenance/maturity contracts | Framework values are artificial; the five-enzyme showcase uses separately labelled literature-reported inputs but remains unvalidated. |
| Coupled hydrolysis and substrate transglycosylation | Implemented as a generic process law with one provenance-backed fungal-enzyme configuration | The transfer-product pool is unresolved; no product-linkage assignment, re-hydrolysis, or whole-fungus claim is made. |
| Minimal well-mixed fungal process coupling | Implemented and software-tested | Caller-supplied degradation, capability, assimilation, secretion, uptake, yield, and maintenance inputs remain exploratory; no organism-specific physiology or validation is bundled. |
| Conserved growth and substrate maintenance respiration | Opt-in advanced API, software-tested | Balanced growth/maintenance pathways, oxygen/nitrogen-limited batch/chemostat dynamics, gas transfer and open exchange ledger. Missing kinetic parameters remain explicit; no death or regulation. See [new-data comparison](respiration-benchmark.md). |
| Conserved secretion–digestion–growth feedback | Opt-in advanced API, software-tested | Seven pools share balanced growth, maintenance, protein synthesis, hydrolysis and inactivation. Explicit allocation, chemistry, kinetic parameters, analytic Jacobians and batch thresholds. No empirically validated whole fungus, default parameters, dynamic regulation or spatial morphology. See [integrated model](degrading-culture.md). |
| Dynamic single-process thermodynamic constraints | Implemented | Configured enforcement remains ideal-dilute and forward-rate blocking. |
| Haldane relations linking kinetic parameters to equilibrium | Implemented | Uni-uni reversible Michaelis-Menten only; multi-substrate reactions are rejected rather than approximated. Constrains parameters and detects thermodynamically impossible sets; supplies no rate. |
| Gibbs-energy biomass yield ceiling | Implemented and wired into fungal coupling | An upper bound assuming reversible zero-dissipation growth, not an estimate. Both Gibbs energies must be sourced; the bound is opt-in and inverts no existing behaviour. |
| Conservation-law macrochemical balance and entropy budget | Implemented and software-tested as a low-level chemistry API | Solves the unfixed coefficients of an overall conversion from element and charge conservation, then forms reaction Gibbs energy, enthalpy, entropy production, and the heat/matter entropy split from sourced formation energies. Underdetermined or inconsistent balances fail closed. Compositions, formation energies, yield or dissipation, and the extent rate are caller inputs; energies are used as given for their declared conditions. No rate, no yield estimate, no extremal entropy principle, and no coupling into configured or whole-fungus models yet. |
| Genome-derived enzymatic capability resolution | Implemented; connected to user data (USERDATA-003, USERDATA-007) | CAZy family to enzyme-class join from an offline dbCAN annotation, or from the CAZy cross-references and EC numbers of a UniProtKB proteome export (EC numbers resolve only through registry records; a protein whose CAZy and EC annotations name different classes supports neither and is reported with both; an optional client fetches the export from the UniProt REST API only on explicit `refresh=True`, into a digest-checked snapshot, with field names not verified against a live response). Presence and absence only: no rate, kinetic constant, expression level, or secretion claim. Polyspecific families are reported separately from diagnostic ones. A user dataset's `genomes.csv` now feeds a strain's annotation into `VirtualExperiment(user_data=...)`: resolved classes with a registry record join the strain, every one without kinetics becomes explicit gaps with measurement requests that name the annotation, and classes without a record and unmapped families are reported. The registry's `cellobiohydrolase` record (EC 3.2.1.91, alias 3.2.1.176; categorical metadata without kinetics, USERDATA-008) makes GH6/GH7 cellobiohydrolases gaps on solid cellulose substrates instead of unmodellable classes; the records `endo_xylanase` (EC 3.2.1.8; GH10, GH11), `glucoamylase` (EC 3.2.1.3; GH15) and `chitinase` (EC 3.2.1.14; GH18) do the same on the registry's generic solid polymers `xylan`, `starch` and `chitin` (REGISTRY-002; categorical metadata without kinetics; see [registry polymers](user-data.md#registry-polymers)); endoglucanase, LPMO, cellobiose dehydrogenase, laccase, class II peroxidase, acetyl xylan esterase, alpha-amylase and pectate lyase have no record. The genome route assigns no rates. See [genome annotation](user-data.md#genomescsv-optional-enzyme-classes-from-a-genome-annotation) and [UniProt proteome](user-data.md#from-a-uniprot-proteome). |
| Constant-coefficient nonideal reversible thermodynamics | Implemented as a separate low-level API | Coefficients and the forward kinetic scale must be sourced; no electrolyte model or configured assembly is inferred. |
| 1D and uniform Cartesian 2D/3D reaction diffusion | Implemented and software-tested | No irregular mesh, porous morphology, moving boundary, or empirical spatial validation. |
| Continuum mycelium on the compiled spatial core (tip extension, tip motion, branching, anastomosis, losses, uptake, translocation, secretion) | Exploratory, software-verified (`fungal_model.mycelium`) | Densities on a uniform Cartesian (one to three axes) or axisymmetric radial grid; no individual hyphae, moving boundary or morphology; not reachable from the registry or `VirtualExperiment`; no organism parameters. The colony comparison has a frozen plan and a recorded, passed stage 0 (software checks) but no fit or validation yet. See [spatial mycelium](spatial-mycelium.md) and the [colony comparison plan](colony-comparison.md). |

## Data, curation, and validation

| Capability | Status | Boundary |
| --- | --- | --- |
| Offline-first SABIO-RK proposals | Implemented | Proposals are review-only and never mutate the registry. |
| Curator decision bundles and signatures | Implemented | Acceptance is not scientific validation or simulation authorization. |
| Transactional registry promotion | Implemented | Promotion requires exact reviewed bytes and explicit writable targets. |
| Generic least-squares calibration utilities | Implemented | No parameters are calibrated by default. |
| Configured calibration against synthetic and literature datasets | Implemented | Toy, framework, calibrated, and validated dataset maturities fail closed. Fitting a published dataset is parameter estimation; a literature fit carries its own non-validation assumptions and warnings. |
| Calibration evidence audit | Implemented | A pass means declared software criteria passed; publication authorization is always false. |
| Posterior sampling and identifiability verdicts on the compiled core | Implemented; one retrospective registry-case study | Affine-invariant ensemble sampling over explicit log-uniform or uniform priors and explicit Gaussian error models, optional estimated noise-scale multipliers, autocorrelation and effective-sample diagnostics, declared-threshold classes (`identified`, `weakly_identified`, `bounded_above_only`, `bounded_below_only`, `prior_dominated`), local Fisher information and posterior predictive bands. The *T. harzianum* cellulose study reports which of its nine constants the duplicate-mean data identify; its error model is an assumption because no replicate-level data exist, and no verdict is validation. See [Bayesian calibration](bayesian-calibration.md). |
| Synthetic-data utilities | Implemented for software tests | Synthetic data must never be presented as scientific evidence. |
| First literature time-course comparison | Implemented for one same-source no-refit consistency check | The nine digitized observations and source-model parameters are not independent validation; digitization resolution is not experimental uncertainty. |
| Held-out condition study across all four Figure S1 series | Implemented for one publication | Four series, 36 digitized observations, from one figure by one laboratory. Held-out agreement shows transfer across experimental conditions, not independent replication. |
| Three independent literature sources, seven series, four enzyme preparations | Implemented | Alvarez-Gonzalez 2022 (60 min), Ariaeenejad 2020 (380 h), Cao 2015 (10 h). Only the first supplies additional conditions for within-source prediction; the other two support exploratory fitting, not predictive validation. |
| Whole-culture biomass/substrate benchmark | Six Gelain 2020 conditions; source-model projection and fitted effective growth/loss hypothesis | 96 non-initial observations for T. harzianum P49P11, six retrospective condition holdouts plus weighting sensitivity. Missing replicate errors, substantial cellulose prediction errors; no validated organism model. See [benchmark](gelain-culture-benchmark.md). |
| Public secretome source intake | Novy 2021 workbook preserved | Endpoint normalized spectra for T. reesei QM6a support composition review, not absolute enzyme concentration, secretion rates or kinetic parameters. |
| A. niger growth/respiration source intake and holdouts | Two primary articles preserved and checksummed | Four unreconciled chemostat conditions support bounded exchange-rate holdouts; six single-substrate and eleven mixed-substrate conditions provide separately labelled references/gap diagnostics. External batch transfer fails; reconciled rates do not independently validate conservation. |
| A. niger extracellular protein output | One additional primary article, four group means and reported SDs | Entire-strain holdouts compare pooled versus carbon-source-dependent ratios at a supplied growth rate. Sequential substrate conditions share cultures. Total protein is not active enzyme; component evidence does not calibrate the integrated degradation model. |
| Cross-source exploratory fits with numerical diagnostics | Implemented | Fits five selected series and reports convergence attempts, bound proximity, and Jacobian conditioning for both candidate models. Local diagnostics do not establish identifiability, structural adequacy, or a biological mechanism. |
| Monte Carlo, local, and global sensitivity | Implemented | Global indices assume independent explicit input distributions; no empirical biological distribution is supplied. |

## Not currently supported

- complete arbitrary fungus/substrate/environment prediction. Capability
  resolution now covers any organism with a CAZyme annotation or a UniProt
  proteome export and is connected to virtual experiments through a user
  dataset's `genomes.csv`, but capability
  is not modellability: for a typical white-rot repertoire five of ten
  resolved enzyme classes currently have a registry record (beta-glucosidase,
  cellobiohydrolase, generic cellulase, endo-xylanase and chitinase), and the
  rest (LPMO, cellobiose dehydrogenase, acetyl xylan esterase, laccase and
  class II peroxidase) are reported as present-but-unmodellable rather than
  silently dropped. A record is categorical metadata, not kinetics: the genome
  route assigns no rates, and every resolved class needs measured or curated
  kinetics before it can run;
- any rate predicted from thermodynamics. Gibbs energy fixes direction,
  equilibrium, parameter coupling, and a yield ceiling. It does not fix rate,
  which depends on an enzyme's activation barrier: two enzymes catalysing one
  reaction share an equilibrium constant exactly while differing in maximal rate
  by orders of magnitude;
- an integrated whole-fungus model of secretion, uptake, regulation, transporters,
  toxicity, respiration and intracellular metabolism. The new opt-in
  macrochemical APIs now couple growth, respiration, secretion and hydrolysis,
  but lack validated regulatory, intracellular and spatial physiology;
- publication-grade calibration and broad external validation;
- predictive validation on the second and third literature sources. Each of
  those provides a single condition per enzyme, so the model can be fitted to
  them but not tested out-of-sample against them. Only Alvarez-Gonzalez 2022
  supplies a genuine held-out condition;
- transfer of pNPG assay constants to cellobiose. Earlier PersiBGL1 fit results
  fixed a pNPG Michaelis constant and are superseded. The current study estimates
  the unknown cellobiose constant and treats the fit as exploratory. Its
  inhibition parameters cannot establish a contradiction with a different assay;
- validated transfer across enzyme loading. The Alvarez-Gonzalez panel-B
  predictions have unresolved residuals and depend on an assumed mg/L reading
  of a caption printing mg/mL. Candidate deactivation and enzyme-scaling fits
  are reported by `scripts/run_alvarez_gonzalez_2022_mechanism_hypotheses.py`, but
  do not confirm or falsify either mechanism or uniquely attribute the residuals
  to model structure. Additional observations and resolved assay metadata are
  needed before making validation claims;
- coupled-network thermodynamic flux optimization;
- state-dependent electrolyte/activity-coefficient models;
- correlated-input global sensitivity;
- Bayesian calibration beyond bounded uniform or log-uniform priors,
  Gaussian observation-error models and the gradient-free ensemble sampler
  of `fungal_model.calibration.bayesian`;
- irregular spatial models and dynamic morphology;
- resolved PET MHET/BHET/TPA/EG product chemistry;
- validated default models for lignin, starch, chitin, or full
  lignocellulose.

Unsupported scope should remain explicit in preflight, limitations, or errors.

## Research reproducibility additions

- SBML supports explicit numeric unit conversions; PEtab preserves split membership and rejects unknown noise scales.
- SBML export covers proportional synthesis, parameter-bound stoichiometric coefficients (as separate reactions) and assay-activity units (as named dimensionless definitions); `conditions_to_petab` exports multi-condition problems from assembled models, and `fungal_model.standards.copasi` reproduces them in COPASI with the column weights corrected to `1/sigma^2`.
- Calibration supports grid profile likelihood under explicit independent Gaussian observation scales, with failures and local-optimum limitations reported.
- Frozen-prediction evaluation checks artifact hashes, raw replicate means, supplied experimental uncertainty and sourced RMSE criteria without refitting. No independent empirical dataset is bundled, and publication authorization remains false.
- Exploratory inhibition runners share package integration and the configured inhibition denominator; exponential activity loss remains a study hypothesis.
