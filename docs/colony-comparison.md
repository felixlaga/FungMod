# Colony comparison plan (COLONY-001)

The first scientific use of the spatial mycelium core (SPATIAL-001) is a
within-study transfer test against the colony growth curves of De Ligne et
al. 2019 (DATA-003): hourly mycelial area and tip count of *Coniophora
puteana* and *Rhizoctonia solani* under sixteen temperature-humidity
conditions. The test is declared before anything is run, in
`data/benchmarks/de_ligne_2019_colony/plan.json`, and
`tests/test_colony_comparison_plan.py` pins that file's SHA-256
(`e7a8706e85fef7739e96c7fe21d8aac0cbf2e4719201b1c203c9296d033066e4`), so
a change to the plan is impossible without a dated amendment inside the
file and a new digest in the test and the ledger.

**Status:** plan frozen on 2026-10-06. Of the stage 0 software, the
axisymmetric grid, the observation operators and the cardinal water-activity
law exist (SPATIAL-002); the error-model fit, the study runner and the
recorded stage 0 checks do not, and no fit has been run. Nothing on this page
is a result.

## The question

Can the continuum mycelium, with one dimensionless environment activity per
condition multiplying tip extension and branching, reproduce the area and
tip-count curves of one species across the sixteen conditions, and predict
four held-out conditions from the activities fitted on the other twelve
through cardinal response laws in temperature and water activity?

## What the plan declares

- **Geometry.** The colony is axisymmetric: one radial coordinate from the
  centre of the inoculum disc (radius 5 mm, the 1 cm agar disc) to the
  half-diagonal of the 40 x 40 mm scan window, in 0.1 mm cells with no-flux
  ends. Stage 0 must show that this agrees with the two-dimensional
  Cartesian model of SPATIAL-001 within 3 percent on both observables, and
  that halving the cell and switching the solver change nothing material.
- **Model.** `colony_reserve_v1`: tips, hyphae, an internal reserve carried
  by the mycelium and the inoculum reserve it draws on (the Petri lid is
  inert, so the disc is the only source), with the SPATIAL-001 processes:
  saturating extension that pays for the length it lays down, tip
  diffusion, lateral branching that needs internal reserve, anastomosis,
  tip loss, uptake from the disc, diffusive and active translocation. One
  activity `phi_c` in [0, 1] per condition scales the extension speed and
  the branching rate; every other parameter is shared across conditions.
  A comparison variant gives extension and branching separate activities
  and must pass the complexity screen of the criticism plan to be
  preferred. Every bound is an explicit exploratory search range, not a
  measured constant; the inoculum reserve and the initial tip and hyphal
  densities inside the disc are explicit unknowns because the source
  removed the disc from every image.
- **Observation operators.** Tip count is the tip density integrated over
  the colony outside the disc and inside the window, because the source
  counted graph nodes of degree one after removing the disc. Mycelial area
  is the window-truncated disc of the outermost hyphae whose length density
  reaches one segment per model cell, never smaller than the inoculum disc,
  because the source's area is the convex hull of all graph nodes
  including the artificial nodes on the disc boundary. Neither observable
  is biomass or hyphal length.
- **Error model.** A per-series linear standard-deviation model fitted to
  the readable, two-sided bar readings and applied to every hour, floored
  at the digitization resolution; rows flagged `panel_disagreement` are
  excluded; one shared noise multiplier in the posterior stage.
- **Hold-outs.** Conditions (15 C, 75 %), (20 C, 65 %), (25 C, 80 %) and
  (30 C, 70 %): each temperature and each humidity level is held out
  exactly once, the same four for both species, chosen before any fit.
- **Stages.** 0: software and checks. A: one joint weighted least-squares
  fit per species of the shared parameters and the twelve training
  activities, with the criticism plan's optimiser settings. B: cardinal
  response laws (Rosso CTMI in temperature; the Rosso and Robinson 2001
  cardinal water-activity model with `a_w = RH / 100`, an equilibrium
  assumption the plan names) fitted to the twelve activities, every law
  parameter classified with the BAYES-001 identifiability thresholds. C:
  the four held-out conditions predicted from the laws, written with the
  plan digest before they are scored. D: the ensemble posterior with
  predictive coverage, only if stage A reproduces.
- **Decision rules.** R1 reproduces: root-mean-square standardised residual
  at most 2.0 over the training conditions for both observables. R2
  transfers: the held-out value at most 1.5 times the training value. R3
  identified: the environment-scaled rates and every law parameter
  identified or weakly identified. R4 coverage: reported, not thresholded.
  Outcomes use four phrases only: reproduces and transfers, reproduces but
  does not transfer, does not reproduce, not run with its reason; a passing
  outcome that fails R3 carries the qualifier "unidentified" and promotes
  nothing.

## Why a frozen plan before the software

The feasibility run that sized this plan (the artificial colony of
SPATIAL-001 on a 40 x 40 mm Cartesian grid of 1 mm cells, 62 h) took about
three minutes per solve, which puts a joint fit over twelve conditions out
of reach; the axisymmetric grid is the planned remedy and its agreement with
the Cartesian model is the first check of stage 0. Declaring the operators,
the error model, the hold-outs and the rules now keeps those later
engineering choices from being tuned to the data.

## What it is not

One experiment, one laboratory, one figure per species: agreement across
the sixteen conditions is within-study transfer, never independent
replication or biological validation. No transfer to other strains,
substrates, submerged culture or three dimensions is claimed. The humidity
law is an empirical shape under a declared equilibrium assumption, not a
mechanism. Hyphal geometry (segment length, angles, diameter) is neither
modelled nor compared. No fitted constant is promoted to a registry record
beyond a retrospective fit labelled with this plan.
