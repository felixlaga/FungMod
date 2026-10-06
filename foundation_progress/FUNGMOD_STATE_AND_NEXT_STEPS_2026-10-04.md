# FungMod: verified state, gaps to "full fungus", and next steps

Assessment date: 2026-10-04. Everything below was checked against code, tests and
measurements on the current `main` (commit 50f8496), not against roadmap text.

## 1. Verdict

FungMod is a well-engineered, honest *framework* with very little *fungus* in it.
About four fifths of the code is registry, curation, provenance, output-table and
report infrastructure. The mechanistic core is small, and the whole-organism
physiology that exists lives in three separate opt-in classes that the
researcher-facing `VirtualExperiment` API cannot reach. The shipped registry
contains no real fungus. In `scientific` mode, zero cases are runnable.

A top-tier biology or computational-biology journal publishes a validated
biological result, not a framework. The project's own `docs/paper-readiness.md`
correctly targets JOSS (a software journal). Reaching Nature Methods, Nature
Computational Science, Cell Systems or Molecular Systems Biology requires at
least one prospectively validated prediction on real fungi. That requires
first fixing the solver layer, then binding physiology to the registry, then a
wet-lab collaboration.

## 2. What it can do today (verified)

Quality gates on this checkout: ruff clean, pyright clean (0 errors),
pytest 1685 passed / 11 failed in 18m41s on Python 3.11, numpy 2.4.6, scipy 1.17.1, libsbml 5.21.2.
The 11 failures are dependency-version and test-order sensitivity, not
model bugs. Nine SBML cross-engine/unit tests pass in isolation but fail in
the full run; the BioModels round-trip test fails even alone (libsbml 5.21
SWIG returns an opaque enum from `getType()` that the reference AST
evaluator in `standards/cross_engine.py` cannot compare); one frozen Gelain
holdout replays to 4.4e-6 relative difference against a 2e-6 gate under
scipy 1.17 (the lock file pins 1.18, CI installs unpinned, and libsbml is
not pinned at all). Four curator-authoring tests take ~110 s each.

| Measured fact | Value |
| --- | --- |
| Source lines | 62.7k (tests 38.9k, 1266 test functions) |
| Infrastructure packages (api, screening, data, workflows, sources, registry, io, standards, calibration) | ~40k lines |
| Mechanism/physics packages (processes, kinetics, solvers, fungi, chemistry, transport, geometry, modifiers) | ~12k lines |
| Registry fungus records | 3: one toy, two "enzyme-source pseudo-records". No real organism. |
| Registry substrates / enzyme classes / environments | 3 / 3 / 3 |
| Fungus x substrate x environment combinations | 27 |
| Runnable in `exploratory` mode | 3 (one of them the toy) |
| Runnable in `scientific` mode | 0 |
| Shipped case templates with any environment response law bound | 0 (temperature/pH grids are metadata only) |
| Parameter records | 24: 12 exploratory priors, 6 toy, 4 literature-processed, 2 literature ranges |

Implemented and software-tested mechanisms:

- Enzyme-only soluble kinetics: first-order, mass action, homogeneous
  Michaelis-Menten, competitive / Haldane / product inhibition,
  transglycosylation branch, linear/branching/cyclic enzyme chains.
- Surface catalysis: equilibrium Langmuir coverage times constant accessible
  area. No surface erosion, no enzyme depletion by binding, no crystallinity.
- Environment modifiers: Arrhenius, Gaussian pH, Monod oxygen, water-activity
  threshold. Implemented, but bound to nothing shipped. No thermal
  inactivation of enzymes.
- Thermodynamics: macrochemical element/charge balance, Gibbs yield ceiling,
  single-reaction feasibility blocking, closed detailed-balance network with
  equilibrium solver, Haldane relations. All constraint layers; no rate.
- Whole-fungus physiology (three separate opt-in classes, none registry-bound):
  `FungalCouplingModel` (secretion/decay/uptake/maintenance, kg + mol/L mix),
  `ResourceLimitedCulture` (Pirt growth + maintenance, O2/N limitation, gas
  transfer, chemostat), `DegradingCulture` (7 pools, costed secretion,
  hydrolysis, inactivation, analytic Jacobian).
- Spatial: uniform Cartesian 1D/2D/3D reaction-diffusion on fixed grids. No
  hyphae, tips, branching, or moving boundaries.
- Uncertainty: Monte Carlo, local sensitivity, Saltelli/Jansen global
  sensitivity (independent inputs only). No Bayesian calibration.
- Calibration: least squares, grid profile likelihood, frozen-prediction
  evaluation contract, SBML/PEtab/COMBINE export.
- Data: 7 beta-glucosidase progress curves from 3 papers (digitized), Gelain
  2020 T. harzianum cultures (6 conditions, 144 means, no replicates),
  Lameiras 2015/2017 A. niger chemostat rates, Jorgensen 2009 protein output
  (4 means), Novy 2021 T. reesei secretome (composition only).

Every empirical comparison is retrospective. The best-scoring culture model in
the Gelain benchmark is a refit of Gelain's own published equations.

## 3. The solver problem, concretely

The feeling that the solvers are "all over the place" is accurate. There are
three incompatible model representations and at least seven integration paths.

| Path | Model representation | Reachable from VirtualExperiment? | Jacobian | Per-RHS cost (measured) |
| --- | --- | --- | --- | --- |
| `solvers/process_ode.py` ProcessODESolver | `Process.rate()` + `contributions()` on dicts of pint Quantities | Yes (only path that is) | finite difference | ~0.5 ms vs 16 us numpy (~30x) |
| `core/simulation.py` SimulationEngine | `Reaction` callables on pint dicts | No | finite difference | same pattern |
| `transport/reaction_diffusion.py` 1D | `Reaction`, Python loop over cells, pint per cell | No | sparse pattern only | 200 cells: 3.9 s for 59 RHS evals (66 ms each) |
| `transport/reaction_diffusion_nd.py` 2D/3D | `Reaction` on whole-field Quantities | No | sparse pattern (pure diffusion only) | pint per RHS |
| `fungi/respiration.py` ResourceLimitedCulture.simulate | hand-written numpy kernel | No | analytic | fast |
| `fungi/degradation.py` DegradingCulture.simulate | hand-written numpy kernel, N @ v + boundary | No | analytic | 19 states, 3205 evals in 0.5 s |
| `chemistry/detailed_balance.py` | hand-written numpy kernel | No | analytic | fast |
| `research/gelain_*.py`, `inhibited_progress.py`, `standards/cross_engine.py` | ad hoc `solve_ivp` calls | No | none | n/a |

Consequences:

- The only path a researcher can reach costs 0.8 s per sample for a
  three-state Michaelis-Menten model (writing a full bundle per sample). A
  1000-sample ensemble over a 4x4 environment grid is about 3.5 hours for the
  simplest possible case. Bayesian calibration, which needs 10^4 to 10^6
  solves, is out of reach on this path.
- The spatial engines evaluate pint arithmetic inside the RHS. A 50x50 grid is
  minutes per solve. Hyphal morphology models need thousands of solves.
- The physiology that actually makes it a fungus model is unreachable from the
  registry, the configured workflow, modelability preflight, the output tables,
  the ensemble machinery and the sensitivity tools. `grep` confirms only
  `io/yaml_loader.py` imports `fungal_model.fungi`, and only for metadata.
- Units are resolved per RHS call rather than once at build time. Each engine
  has its own tolerance semantics, negativity policy and result object.
- Only the hand-written kernels have analytic Jacobians; the generic paths do
  not, so stiff problems are slow or fail (the audit's BDF depletion failure).

The good news is that `DegradingCulture` already contains the right design:
a stoichiometric matrix, a numpy rate vector, boundary terms, an analytic
Jacobian and a conservation ledger. It just is not generic.

## 4. Gaps to "full fungus modelling" at a top-journal standard

1. **No organism.** The registry has no fungus record with secretion, uptake,
   yield, maintenance or growth-response parameters. The "fungi" are enzyme
   sources.
2. **Environment does nothing.** Temperature and pH grids are metadata in every
   shipped case. There is no cardinal-temperature or pH growth-response model
   with sourced parameters, and no thermal inactivation.
3. **Physiology is triplicated and isolated.** Three whole-fungus models, three
   unit conventions, none composable with the enzyme processes or reachable
   from the public API.
4. **Solid substrates are placeholders.** Cellulose, lignin, starch and chitin
   classes carry unknown metadata and no accessibility, crystallinity, erosion
   or lignin-shielding model. The only solid case is a generic exploratory
   film.
5. **No spatial fungus.** Fixed-grid reaction-diffusion is not a mycelium.
   Tip extension, branching, anastomosis, translocation and colony-boundary
   coupling do not exist.
6. **All validation is retrospective.** No replicate-level data, no measured
   error model, no prospective held-out experiment, no cross-species transfer
   test. The project's own evaluator keeps `publication_claim_authorized`
   false, correctly.
7. **Bayesian inference exists only on assumed errors.** Posterior sampling,
   identifiability classes and local information exist since BAYES-001
   (2026-10-05); every error model is still an assumption because no
   replicate-level data exist, and identifiability-aware model selection does
   not exist.
8. **Scale.** The public path cannot run the ensemble sizes the central-goal
   document promises in acceptable time.

## 5. Next steps, in order

### Step 1. One compiled model core (prerequisite for everything else)

Replace the three representations with one intermediate representation that
every front end compiles to and every engine consumes:

- Ordered state vector with units resolved once at build time.
- Stoichiometric matrix N (states x processes) and a numpy rate vector
  v(t, y, p), so dy/dt = N v + boundary(t, y).
- Optional analytic or autodiff Jacobian, conservation matrix, and a single
  `SimulationResult`.
- `Process`, `Reaction`, the three physiology classes and the Gelain research
  models become builders that emit this IR. `SimulationEngine` is retired.
- Spatial engines apply the same IR per cell with vectorized rates and a
  diffusion operator, no Python loop over cells.
- Units are checked at compile time; the RHS is pure numpy.

Target: the Reaction 618 case drops from ~0.8 s to a few ms per sample, and the
7-pool culture model becomes a registered process family rather than a
special class. Keep the existing tests as the parity oracle.

### Step 2. Put a real fungus in the registry

Promote the `DegradingCulture` physiology into registry-driven process
templates with parameter roles, and author records for the three organisms the
data already cover: T. harzianum (Gelain), A. niger (Lameiras, Jorgensen),
T. reesei (Novy composition, Pakula 2016 time courses as the next intake).
Definition of done: at least one organism x substrate case runs in
`scientific` mode through `VirtualExperiment`, with biomass, enzyme, substrate
and product trajectories in `time_series_long.csv`.

Status 2026-10-05 (ORG-001): done for T. harzianum P49P11 on Celufloc 200
cellulose, with one deviation. The registry case composes generic process laws
(`culture_physiology` template, new `proportional_synthesis` process) and binds
the nine constants of the frozen Gelain hydrolysis candidate as `calibrated`
records; it reproduces the research implementation and runs in `scientific`
mode for all three cellulose loadings. The deviation: the data hold no measured
product, so the case has no product pool; consumed cellulose not retained as
biomass is an explicit closure ledger. Not done: the Pirt/Monod resource-limited
growth, maintenance and costed-secretion closures of `DegradingCulture` are not
registered (no organism parameterizes them), and A. niger and T. reesei have no
registry records because the data carry no enzyme-class evidence (A. niger) or
no time courses (T. reesei). See `progress.md` ORG-001.

### Step 3. Make environment grids mean something

Bind cardinal-temperature (Rosso-type) and pH growth-response laws with
sourced parameters for those organisms, plus enzyme thermal inactivation.
Without this, the central promise "how does pH or temperature change
degradation dynamics" is unfulfillable.

Status 2026-10-05 (ENV-003): partially done. The laws exist and are bindable:
Rosso CTMI and CPM modifiers, a diprotic pH-ionization Michaelis-Menten
process law (the SABIO-RK pH-dependent law form) and first-order Arrhenius
thermal inactivation, all compiled, tested and reported through
`provenance.environment_response` and `environment_effect_status:
active_response_model`, with environment ranking allowed only across
conditions a law covers. The first sourced binding is enzyme-level, not
organism-level: P. chrysosporium BGL1A on cellobiose over pH 4-8 (SABIO-RK
entry 38522, Tsukada 2008), exploratory mode only because the assay loadings
are assumptions. Not done: no sourced cardinal temperatures, cardinal pH
values or inactivation energies exist in the repository for T. harzianum
P49P11 or its activity pools, and the session's network policy denied every
publisher host, so those laws are bound to no organism; a candidate review
names the sources found. See `progress.md` ENV-003.

### Step 4. Identifiability and Bayesian calibration on the fast core

With a compiled core and Jacobians, add posterior sampling (MCMC or
simulation-based inference) with explicit measurement-error models and
replicate-level data. Recover raw replicates for Gelain and Pakula first. Report
which parameters the data identify and which the model must leave as ranges.

Status 2026-10-05 (BAYES-001): partially done. Posterior sampling exists on
the compiled core (`fungal_model.calibration.bayesian`: explicit priors,
explicit Gaussian error models with an estimated noise multiplier, the
Goodman-Weare ensemble sampler, autocorrelation and effective-sample
diagnostics with a declared convergence rule, identifiability classes with
declared thresholds, finite-difference Fisher information, posterior
predictive bands, pooled replicate deviations) with a predictor that rebuilds
a registry case per candidate. The recorded study
(`data/benchmarks/gelain_2020_bayesian/`) samples the nine T. harzianum
hydrolysis-candidate constants over the three Gelain loadings.
Converged by the declared rule (24 walkers x 24000 steps), it identifies five of the nine constants (k_h, Y, kd, qF, qB), bounds Kh from below only and K_ind, kF, kB from above only, and estimates a shared noise multiplier of about 2.2; the nine registry records cite it in their provenance without changing their point values. Not done: replicate recovery (the Gelain deposit holds
duplicate means only; Pakula 2016 could not be retrieved under the network
policy and is a candidate review), so the error model is an assumption whose
overall level is estimated from the residuals; Jacobians and parameter
sensitivities (sampling is gradient-free and rebuilds the config per
candidate, `FD-010`). A per-observable multiplier variant, not converged and
cited by nothing, shows that the hydrolysis candidate cannot fit biomass and
cellulose simultaneously at the assumed error level. See `progress.md`
BAYES-001.

### Step 5. The scientific result without a wet lab (this is the paper)

Decision 2026-10-05: the first paper is a software and methods paper built on
published data only. No new experiments are planned, because no laboratory is
available. The long-term goal of modelling all fungi stands and is restated
after step 6. Every claim below is retrospective and must be labelled so.

Ordered work, each with an exit gate:

1. **Green CI and a merged chain.** Resolve the three failure groups that were
   red on `main` across platforms (reference-simulator SWIG proxy clash after
   `libsedml` import, a holdout replay score tolerance tighter than the
   prediction tolerance it derives from, Windows default-encoding reads and
   backslash path comparisons), then merge PRs #77 to #80 into `main`. Gate:
   every job green on Linux, macOS and Windows for three Python versions.
2. **Model criticism on Gelain 2020 (the computational result).** BAYES-001
   showed the published hydrolysis candidate cannot fit biomass and cellulose
   together at the assumed error level. Declare two to four explicit
   alternative mechanisms (candidates: biomass decay or maintenance, substrate
   accessibility loss, product inhibition of hydrolysis, an induction lag),
   compare them by whole-condition holdouts and posterior predictive checks
   under a plan frozen before any fit, and report which mechanisms the data
   support and which parameters stay unidentified. Gate: the frozen plan, a
   per-mechanism identifiability table, and failed candidates reported.
   Recorded 2026-10-05 (CRIT-001, CRIT-002, `docs/gelain-model-criticism.md`):
   none of the three declared mechanisms passes the holdout screen, none
   restores adequacy, and only the induction memory constant is weakly
   identified; every stage B verdict is provisional because no chain meets
   the convergence rule at the planned length. Gate met with that label.
   Re-recorded 2026-10-05 (CRIT-003): the stage A optimiser had been
   stopping above the minimum (undeclared finite-difference step, found by
   the cross-solver check); under amendment 3 the soluble product pool (M2)
   passes the holdout screen in both scenarios with every observable better,
   while M1 and M3 still fail it. M2's stage B posterior (unchanged,
   provisional) leaves its four constants prior dominated or bounded on one
   side, so its outcome is "improves fit but unidentified (R1, not R3)";
   nothing restores adequacy. Gate still met with the provisional label; the
   M2 chain centred on the new fit is the next study task.
3. **Cross-study transfer from the literature (the intended headline).** Find a
   second published submerged cellulose-culture time course, preferring the
   same organism from another laboratory, then the same genus. Freeze the
   Gelain-calibrated model, predict the second study without refitting, and
   score it under the frozen-prediction contract. Gate: the second dataset is
   checksummed with licence and provenance before any prediction; the
   prediction is frozen before scoring; a failed transfer is reported as a
   result. If no usable dataset exists, the search and its gaps are recorded
   and the transfer claim is withdrawn, not weakened.
   Survey 2026-10-05 (`foundation_progress/TRANSFER_DATASET_SURVEY_2026-10-05.md`,
   abstract level only because the session's network policy blocked every
   publisher and repository): no open raw-data deposit of a submerged
   Trichoderma cellulose batch with biomass, substrate and enzyme time courses
   other than Gelain 2020 was found. The viable targets are figure
   digitizations: Saez 2002 with Schell 2002 (T. reesei on Solka-floc, NREL),
   Velkovska 1997 (T. reesei RUT-C30) and Delabona 2016 (same strain, same
   laboratory, lignocellulose). A digitized time course may serve as the
   held-out target only when its digitization uncertainty is carried
   explicitly and a person with normal web access has read the full texts to
   confirm strain, conditions and replicates.
4. **Cross-solver reproduction through PEtab.** Export the Gelain problem with
   the existing PEtab writer, fit it in an external tool (pyPESTO or COPASI)
   and show the same optimum within a stated tolerance. Gate: one command
   reproduces the external fit and its result is checksummed.
   Recorded 2026-10-05 (PETAB-001, `docs/gelain-cross-solver.md`): COPASI
   reproduces FungMod's simulation to 1.7e-8 of sigma, then finds an objective
   1.3 percent below FungMod's recorded optimum; FungMod evaluates that point to
   the same objective. Outcome `copasi_improves` under the frozen plan: the
   solvers agree, the stage A optimiser stopped early.
   Re-recorded 2026-10-05 (CRIT-003): the stage A optimiser was missing a
   declared finite-difference step (amendment 3 of the criticism plan); after
   the re-run, COPASI's local fit and FungMod's optimum agree to 2.5e-8 and
   every parameter to better than 1e-4. Outcome `reproduced`. Gate met.
5. **Unify the three whole-fungus classes** before adding any physiology, as
   section 6 already demands.
6. **Reproducibility package and preprint.** One command regenerates every
   table and figure; a pinned environment; a PyPI wheel with an offline install
   test; a tagged release with a DOI; AI assistance disclosed; a domain
   researcher reviews the biological mapping. Venues: a bioRxiv preprint as
   soon as items 2 and 4 hold; a methods paper (PLOS Computational Biology or
   Bioinformatics); JOSS only after its six-month public-history window, late
   November 2026 at the earliest (see `docs/paper-readiness.md`).
   Status 2026-10-05 (REPRO-001, `docs/reproducing-the-paper.md`): the
   paper's tables are generated by one command with a digest manifest and
   tiers of reproduction up to a full re-run; the runtime closure is pinned
   and CI installs the wheel offline; the draft manuscript cites the
   generated tables. Open: the tagged release with a DOI (owner), the domain
   review, an independent walkthrough.

What the paper may claim: a provenance-aware, uncertainty-honest
virtual-experiment engine demonstrated on one real organism with
identifiability analysis, model criticism and a frozen-holdout prediction
contract. What it may not claim: validated prediction for untested fungi,
substrates or conditions, or "full fungus modelling".

The wet-lab candidates (prospective prediction, closed-loop experimental
design) are deferred, not abandoned. The frozen-prediction contract remains
the tool for them when a partner laboratory exists.

### Step 6. Spatial mycelium (the "full fungus" step, after 1 to 5)

Hyphal tip extension and branching with local uptake and secretion, coupled to
the compiled reaction-diffusion core, validated against colony-expansion and
microscopy data. This is a multi-year programme on its own and should not start
until a well-mixed organism model is predictive.

### After step 6. Modelling all fungi

The end goal is unchanged: predict degradation by any fungus on any material
under any environment. The table in `docs/paper-readiness.md` states what that
needs: several validated strain, substrate and environment models and
demonstrated transfer between them. Genome annotations alone cannot supply
kinetics. Step 5.3 is the first transfer test; each later organism case must
pass the same frozen-prediction contract before the registry calls it
predictive. "All fungi" is a programme measured in validated cases, not a
feature.

## 6. What to stop doing

- Stop adding output-table, report and diagnostics ergonomics. Thirty files per
  run is already more than any reviewer will read.
- Stop adding opt-in physics layers (nonideal thermodynamics, entropy budgets)
  until a case needs them for a prediction.
- Stop adding single-condition enzyme digitizations; they cannot be tested
  out of sample.
- Do not add a fourth whole-fungus class before the three are unified.
