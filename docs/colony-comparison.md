# Colony comparison plan (COLONY-001)

The first scientific use of the spatial mycelium core (SPATIAL-001) is a
within-study transfer test against the colony growth curves of De Ligne et
al. 2019 (DATA-003): hourly mycelial area and tip count of *Coniophora
puteana* and *Rhizoctonia solani* under sixteen temperature-humidity
conditions. The test is declared before anything is run, in
`data/benchmarks/de_ligne_2019_colony/plan.json`, and
`tests/test_colony_comparison_plan.py` pins that file's SHA-256
(`2ce70b6b21b2d254f4d01d3fb5ec1523442299f2ed6ce2853c270fab712acd9d`), so
a change to the plan is impossible without a dated amendment inside the
file and a new digest in the test and the ledger.

**Status:** plan frozen on 2026-10-06 and amended three times the same day,
before any fit; each amendment is dated in the file with the previous digest
and its reason. Amendment 1 made the area operator's detection density a
grid-independent constant. Amendments 2 and 3 followed recorded stage 0 checks
that failed, and the superseded records are kept as their evidence
(`results/stage_0_superseded_ea6e2e72/`, `results/stage_0_superseded_ca0e016c/`).
The stage 0 software is the study module
`fungal_model.research.colony_comparison` with its runner
`scripts/run_de_ligne_2019_colony_comparison.py` (plan and dataset digest
checks, the per-series error-model fit, the `colony_reserve_v1` model on
either geometry, the two observables and `run_stage_0`), on the axisymmetric
grid, observation operators and cardinal water-activity law of SPATIAL-002.
Stage 0 is recorded under amendment 3 in `results/stage_0/` and passed all
three checks (see "Stage 0 record" below); no fit has been run. Nothing on
this page is a fit result.

## The question

Can the continuum mycelium, with one dimensionless environment activity per
condition multiplying tip extension and branching, reproduce the area and
tip-count curves of one species across the sixteen conditions, and predict
four held-out conditions from the activities fitted on the other twelve
through cardinal response laws in temperature and water activity?

## What the plan declares

- **Geometry.** The colony is axisymmetric: one radial coordinate from the
  centre of the inoculum disc (radius 5 mm, the 1 cm agar disc) to the wall
  of a 9 cm dish (a declared assumption, amendment 3), in 0.1 mm cells with
  no-flux ends; the observables are read on the 40 x 40 mm scan window.
  Stage 0 must show that this agrees with the two-dimensional Cartesian
  model of SPATIAL-001 on the window within 3 percent on both observables
  while the tips have not reached the window walls, and that halving the
  cell and switching the solver change nothing material.
- **Model.** `colony_reserve_v1`: tips, hyphae, an internal reserve carried
  by the mycelium and the inoculum reserve it draws on (the Petri lid is
  inert, so the disc is the only source), with the SPATIAL-001 processes:
  saturating extension that pays for the length it lays down, tip
  diffusion, lateral branching that needs internal reserve, anastomosis,
  tip loss, uptake from the disc, diffusive translocation (the active,
  tip-directed term was removed by amendment 2; see below). One
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
  reaches the declared detection density of one millimetre per square
  millimetre (a grid-independent operator constant), never smaller than the
  inoculum disc,
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

## Amendment 2: the active translocation term was ill-posed

The first recorded stage 0 (2026-10-06, under amendment 1, kept in
`results/stage_0_superseded_ea6e2e72/`) failed two of its three checks at the
artificial check values: halving the radial cell changed the tip count by up
to 57 percent and the area by 10 percent (threshold 2), and the cartesian
reference differed by 76 and 19 percent (threshold 3); the solver check
passed. The failure was the model's. The active translocation term carried
internal reserve up the tip-density gradient, branching made tips where the
reserve was, and the tips aggregated into a spike whose height grew without
bound as the cell shrank, the finite-time aggregation known from
Keller-Segel chemotaxis models:

| Active translocation | 24 h tip count on 141, 283, 566 radial cells | Peak tip density per halving of the cell |
| --- | --- | --- |
| `D_a = 1` | 27 669, 64 922, 146 399 | doubles |
| `D_a = 0.1` | 1 434, 1 301, 1 161 | quadruples |
| `D_a = 1e-4` | 9 617, 9 531, 9 531 | converged |

A fit over the declared bounds of `D_a` could have exploited that grid
artifact. Amendment 2, dated and recorded before any fit, removes the active
term and its parameter from `colony_reserve_v1`, adds a well-posedness guard
that re-solves every scored solution (stage 0 check values, every stage A
optimum, every stage C prediction, the stage D posterior median) on the
doubled radial grid with the 2 percent threshold, adds decision rule R0 that
reports a failure as "not run (not grid converged)", and makes the 3 percent
symmetry threshold the plan already stated machine-readable. The
translocation process now declares the aggregation as a failure mode
whenever its active term is used.

## Amendment 3: the radial wall belongs at the dish, not at the window

The stage 0 re-run under amendment 2 (`results/stage_0_superseded_ca0e016c/`)
passed its grid check (5.3e-5 in tip count, 0.0056 in area, threshold 0.02)
and its solver check (1.1e-7, threshold 0.005), and failed its symmetry check
(0.382 in tip count, 0.059 in area, threshold 0.03). The radial and cartesian
models agreed within 1 to 3 percent until about 12 h and then diverged,
because the two domains differed. The cartesian reference was the 40 mm scan
window, with walls that reflect tips back into it. The radial domain ended at
the window's half-diagonal, 28.3 mm, with a wall of its own. Neither wall is
physical: the window is the scanner's field of view inside a larger dish.

| Probe at the stage 0 check values | Tip count | Area |
| --- | --- | --- |
| 28.3 mm against 45 mm radial wall, largest relative difference over 62 h | 0.46 | |
| 45 mm against 90 mm radial wall, largest over 62 h (below 0.001 until 36 h) | 0.041 | 0.0052 |
| 0.5 mm cartesian reference against the radial model, hours 1 to 12 | 0.027 | 0.058 (at 2 h) |

The radial tip front also runs ahead of the detected colony edge: when the
hull is at 16.65 mm (14 h), 99.9 percent of the tips lie within 21.35 mm, so
tips reach the cartesian walls well before the detected colony does.

Amendment 3, dated and recorded before any fit:

- the radial domain ends at the wall of a 9 cm Petri dish (45 mm, 450 cells of
  0.1 mm). The article does not state the experimental dish diameter, so 9 cm
  is a declared assumption: it is the diameter of the mother-culture dishes
  the article names, and six such dishes, the number scanned at once, fit the
  scan bed of the scanner it names;
- the 40 mm scan window is declared separately, as the square on which both
  observables are read;
- the symmetry check compares the radial model with a 0.25 mm cartesian
  reference on the window (half the 0.5 mm cell, whose area difference at 2 h
  is consistent with the hull's quantisation to cell centres), only over the
  leading output hours at which at most 0.1 percent of the radial tips lie
  beyond the window half side. On the reference that admits hours 1 to 12; at
  least eight compared hours are required, and the 3 percent threshold is
  unchanged. This comparison window was recorded before any cartesian result
  at a finer cell was available.

No model term, parameter, bound, operator, hold-out, stage or decision rule
changed. The cartesian reference is costly: about 4 minutes at 0.5 mm and
several hours at 0.25 mm, because the stiff two-dimensional solve
refactorises a 102 400-state sparse Jacobian.

## Stage 0 record

Recorded 2026-10-06 under amendment 3 (plan digest `2ce70b6b...`) in
`results/stage_0/` (`inputs.json`, `checks.json`, `error_models.json`), as
declared: 450 radial cells of 0.1 mm to the 45 mm dish wall, the stage 0
check values (artificial, declared for the checks only, no estimate of either
species) and the 62 output hours. `scripts/run_de_ligne_2019_colony_comparison.py
check` recomputes the error models and verifies the digests.

| Check | Largest relative difference | Threshold | Verdict |
| --- | --- | --- | --- |
| Grid: 0.1 mm against 0.05 mm radial cells, 62 h | 4.0e-5 (tip count), 0.0054 (area) | 0.02 | passed |
| Solver: LSODA against BDF, 62 h | 1.7e-8 (tip count), 0 (area) | 0.005 | passed |
| Symmetry: radial against the 0.25 mm cartesian window reference, hours 1 to 12 | 0.026 (tip count), 0.016 (area) | 0.03 | passed |

The symmetry comparison covered the twelve leading hours at which at most
0.1 percent of the radial tips lay beyond the window half side (7.6e-4 at
12 h, 1.5e-3 at 13 h). An independent probe at the same settings gave the
same differences, and showed that the tip-count difference at 12 and 14 h
(0.027 and 0.053) is the same at 0.5 and 0.25 mm cells: it comes from tips
reflected by the cartesian reference's non-physical walls, not from the
discretisation, which is what the comparison window excludes. The radial
model takes 0.8 s per condition over 62 h (1972 right-hand sides); the 0.25 mm
cartesian reference took 4.1 hours. The error models: 17 of 32 *C. puteana*
and 23 of 32 *R. solani* series are pooled for having too few readable rows.

Passing stage 0 means the software is fit for the comparison: the radial
reduction is converged and agrees with the two-dimensional model while the
colony is inside the window. It says nothing about either fungus. Stage A
(the fits) has not been run.

## What it is not

One experiment, one laboratory, one figure per species: agreement across
the sixteen conditions is within-study transfer, never independent
replication or biological validation. No transfer to other strains,
substrates, submerged culture or three dimensions is claimed. The humidity
law is an empirical shape under a declared equilibrium assumption, not a
mechanism. Hyphal geometry (segment length, angles, diameter) is neither
modelled nor compared. No fitted constant is promoted to a registry record
beyond a retrospective fit labelled with this plan.
