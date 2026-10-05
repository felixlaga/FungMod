---
title: 'FungMod: provenance-aware virtual experiments with identifiability analysis, preregistered model criticism and cross-solver reproduction for fungal substrate degradation'
tags:
  - Python
  - fungal physiology
  - enzyme kinetics
  - mechanistic modelling
  - parameter identifiability
  - reproducibility
authors:
  - name: Felix Laga
    orcid: 0009-0008-8141-8172
    affiliation: 1
affiliations:
  - name: KU Leuven, Leuven, Belgium
    index: 1
date: 5 October 2026
bibliography: paper.bib
---

> **Draft status (2026-10-05).** Software and methods paper draft assembled
> from the recorded studies in the repository. Every number below is taken
> from a checksummed result file named in the text. Items marked *pending*
> are not yet recorded. Human review of the biological interpretation is
> outstanding and is not asserted here. This draft is not a submission.

# Summary

FungMod is a Python package for mechanistic virtual experiments on fungal
and enzyme-mediated substrate degradation. A registry of organisms,
substrates, enzymes, environments and parameter records with explicit
provenance and maturity labels is composed through case templates into
well-mixed process models; a compiled numerical core integrates them with
build-time unit resolution; calibration, Bayesian sampling with
identifiability classes, and preregistered model criticism run on the same
models; and the models export to SBML, SED-ML, COMBINE and PEtab so that
independent tools can simulate and fit them. The package is organised
around one rule: a simulation may report only what its inputs and their
evidence support. Unknown inputs stay unknown, exploratory assumptions are
labelled, software verification is never presented as empirical validation,
and every scientific study is run under a plan frozen and digested before
the first fit.

This paper describes the design and demonstrates it on one real organism:
the batch cultures of *Trichoderma harzianum* P49P11 on particulate
cellulose published with the Gelain et al. deposit [@gelain2020]. We report
(i) a retrospective whole-condition holdout benchmark of the published
hydrolysis candidate, (ii) a posterior-sampling study that classifies which
of its nine constants the published duplicate means identify, (iii) a
preregistered comparison of three added mechanisms, none of which the data
support under the frozen rules, and (iv) a cross-solver reproduction in
which COPASI [@hoops2006] simulates the exported PEtab problem
[@schmiester2021] to within 1.7e-8 of the observation scale and then finds
an objective 1.3 percent below FungMod's recorded optimum, which FungMod
evaluates to the same value. The last result is an honest finding against
our own optimiser's stopping rule, and the paper reports it as such.

# Statement of need

Models of fungal degradation are usually published as bespoke equation
sets fitted to one dataset, with units, parameter provenance and the error
model left implicit. Reusing such a model for another strain, substrate or
reactor requires re-deriving all three. General systems-biology tools
(COPASI, SBML-based simulators, PEtab-based estimation frameworks) solve the
simulation and estimation problems well but do not carry the biological
bookkeeping that a degradation study needs: which constant came from which
assay under which conditions, which assay units cannot be converted to
molarity without a specific-activity measurement, which output is a measured
pool and which is a closure ledger, and which claim the evidence actually
licenses. FungMod supplies that bookkeeping as code, keeps it attached to
every output, and hands the resulting problem to the general tools through
the community standards rather than replacing them.

# Design

## Registry, case templates and maturity

Every biological input is a registry record with a source, a confidence
level, a validity range and notes. Case templates compose records into a
model config for a (fungus, substrate, environment) triple: state roles,
initial-state mappings, product maps with stoichiometric coefficients that
may be bound to parameter records (a biomass yield `Y` and its complement
`1 - Y`), and a list of generic process templates. The first organism case
composes six generic processes (enzyme-explicit Michaelis-Menten
consumption with a yield split, three first-order losses and two
producer-proportional, saturably induced activity syntheses) with no
organism-specific code path. Assay activities (filter-paper units and
beta-glucosidase units) are independent base dimensions of the unit
registry: they cannot be converted to mass or molarity, and a conversion
would have to enter as a sourced parameter.

A run carries a mode (`scientific` or `exploratory`) and every record a
maturity. The scientific mode refuses inputs below its maturity floor; the
exploratory mode runs them and labels the output. The result bundle lists
mechanisms, assumptions, provenance, limitations and suggested experiments
next to the trajectories.

## Compiled process core

Processes declare required and changed states with units and a rate law on
unit-bearing quantities. The compiled core probes the stoichiometric matrix
from each process's contributions, checks linearity in the rate, resolves
every unit conversion once at build time, and integrates
`dy/dt = N v(t, y)` on plain floats with SciPy's LSODA [@virtanen2020].
Every shipped process and modifier supplies a numeric kernel that
reproduces the unit-aware arithmetic in the same operation order; a process
without one uses the recorded unit-aware fallback, never silently.
Trajectories and evaluation counts are identical to the unit-aware path on
every packaged configuration, and solves are 6 to 60 times faster, which is
what makes posterior sampling and multi-start holdout studies affordable.

## Calibration, posterior sampling and identifiability classes

A configured-condition predictor rebuilds the model config for each
candidate parameter vector, so a yield bound to a fitted parameter reaches
every place the public path puts it. On top of it: multi-start least
squares in log-parameter space with whole-condition holdouts and a
practical-rank diagnostic; an affine-invariant ensemble sampler
[@goodman2010] with checkpointing, autocorrelation-based convergence rules
and a shared observation-noise multiplier sampled jointly with the
parameters; identifiability classes derived from the posterior credible
interval against the prior box (`identified`, `weakly_identified`,
`bounded_above_only`, `bounded_below_only`, `prior_dominated`, with declared
thresholds); local Fisher information at the best sample; and posterior
predictive bands and coverage. The classes are the operational answer to
"what do these data identify" that profile-likelihood analysis
[@raue2009] gives for a single optimum.

## Frozen plans and the claim boundary

Each scientific study is specified by a JSON plan with the data digests,
models, bounds, error model, decision rules, outcome vocabulary and
excluded claims. The plan's SHA-256 is pinned by a test; a change requires
a dated amendment inside the file before any affected run, and every result
cites the digest it ran under. The evaluator that could authorise a
publication claim stays false until replicate-level or independent data
exist.

## Standards and cross-solver reproduction

Models export to SBML Level 3 Version 2 [@hucka2003] with explicit numeric
unit conversions in the kinetic laws, to SED-ML [@waltemath2011] and
COMBINE archives [@bergmann2014], and to PEtab [@schmiester2021]. Two
representation choices keep the exported model faithful where SBML has no
construct: a product coefficient bound to a parameter is written as a
separate reaction whose kinetic law multiplies the process rate by the
parameter (or its complement), so the dependence stays live; and
assay-activity units are written as named dimensionless unit definitions
listed in the model notes, with no SI equivalent implied. A reference
simulator independent of the production path checks every export, and a
COPASI driver imports the PEtab problem, corrects the column weights that
COPASI's importer stores as `sigma` rather than `1/sigma^2`, simulates,
fits, and re-evaluates every optimum on the PEtab objective from COPASI's
own time courses.

# Results on the Gelain 2020 cultures

All results are retrospective analyses of published duplicate means that
already informed model development. None is blind, independent or a
validation of biology. Sources: `data/benchmarks/gelain_2020_v2/`,
`gelain_2020_bayesian/`, `gelain_2020_criticism/` and
`gelain_2020_petab/` in the repository, each with a plan, a README and
digested result files.

## Whole-condition holdouts of the published candidate

The joint benchmark compares seven model and family combinations against
144 published means (biomass, cellulose or glycerol, filter-paper activity
and beta-glucosidase activity) with each condition held out in turn. On the
three cellulose loadings the activity-driven hydrolysis candidate reaches a
mean normalised held-out mean squared error of 0.092 (training-maximum
normalisation) against 0.0062 for the published equations re-fitted with
their own structure; the published structure fails the complexity screen
that the plan declares, the hydrolysis candidate passes it under the
correlated error assumption only. 33 of 33 folds pass the numerical checks;
6 of 132 optimiser starts fail and are reported. No model is promoted to
validated.

## What the data identify

Posterior sampling of the nine registry constants of the hydrolysis
candidate (24 walkers, 24 000 steps, 4 000 burn-in, log-uniform priors on
the declared bounds, one shared noise multiplier) converges by the declared
rule (every autocorrelation estimate reliable, effective sample sizes
1 414 to 2 119, mean acceptance 0.325). The data identify five constants
(the consumption capacity `k_h`, the yield `Y`, the biomass loss rate `kd`
and both specific production rates `qF`, `qB`, with 95 percent credible
intervals of 5 to 16 percent of the prior width in log10), bound the
half-saturation constant `Kh` from below only, and bound the induction
constant `K_ind` and both activity loss rates `kF`, `kB` from above only.
The shared noise multiplier's posterior median is 2.25 (credible interval
1.95 to 2.63) at an assumed 10 percent error, which says that the candidate
cannot fit biomass and cellulose together at that error level. The registry
records keep their frozen point values; the study records which must be
read as ranges.

## Preregistered model criticism

A frozen plan declared three mechanisms that could reduce the
biomass-cellulose misfit, each added to the baseline with its bounds, an
error model, whole-condition holdouts with a complexity screen (at least 10
percent pooled held-out improvement, no observable more than 10 percent
worse, full practical rank), decision rules and an outcome vocabulary.
Stage A (least squares, five starts per fold) found: an induction-state
memory (`M1`) improves the pooled held-out error by 2.7 percent and worsens
cellulose by 13 percent, not supported; a soluble product pool with Monod
uptake and product inhibition (`M2`) improves the pooled error by 23.4
percent but worsens biomass by 31 percent, not supported under the declared
rule; conversion-dependent accessibility [@kadam2004] (`M3`) worsens the
pooled error by 7.9 percent with its exponent driven to the lower bound,
not supported. Every fit has full practical rank. Stage B sampled one
all-condition posterior per addition (24 or 28 walkers, 8000 steps, the
noise multiplier sampled jointly). None of the three chains met the
declared convergence rule at that length, so the plan labels their verdicts
provisional. Under those labels no addition restores adequacy (every
multiplier interval excludes 1.0 and overlaps the baseline's 2.25); only the
induction memory constant of `M1` is weakly identified, while the four
constants of `M2` are prior dominated or bounded on one side and the
exponent of `M3` is bounded above only, driven towards the baseline;
posterior predictive coverage with measurement noise is 91 to 95 of 96
observations. The stated misfit is not explained by any of the three
declared mechanisms.

## Cross-solver reproduction

The baseline problem (three loadings, four observables, 96 measurements,
nine parameters on a log10 scale with the criticism plan's bounds, sigma
equal to each observable's maximum over the loadings) was exported as a
PEtab problem and reproduced in COPASI 4.48 under a frozen plan. FungMod's
objective on the exported problem equals twice its recorded least-squares
cost (4.0307, relative difference below 1e-9). At that point COPASI's time
courses differ from the compiled core by at most 1.7e-8 of sigma over the
96 measurements and the objectives agree to 5e-10. COPASI's
Levenberg-Marquardt fit from the same point then reaches 3.9803, and the
best of ten seeded random starts 3.9768, 1.3 percent below FungMod's
optimum, outside the 0.1 percent tolerance the plan set for agreement.
FungMod's compiled core evaluates COPASI's best point to 3.97682321 against
COPASI's 3.97682324. The solvers agree; FungMod's multi-start least squares
stopped early along a direction (`k_h` against `Kh`, with three loss and
induction constants on their lower bounds) that the posterior study had
already classified as weakly determined. The plan's outcome vocabulary
calls this `copasi_improves`, and the next recorded task tightens the
stopping rule under a dated amendment before any all-condition fit is
quoted as an optimum. No verdict of the criticism study changes by itself,
because its comparisons are relative between models fitted with the same
optimiser, and the posterior study does not rely on the optimum.

# Relation to existing tools

COPASI, SBML simulators and PEtab-based estimation frameworks are the
general infrastructure FungMod exports to, not alternatives to it; the
cross-solver study is the demonstration. Genome-scale metabolic
reconstructions address intracellular flux, not the extracellular
degradation dynamics, assay-defined activities and provenance bookkeeping
that FungMod models. Kinetic databases such as SABIO-RK [@wittig2012]
supply enzyme constants; FungMod imports them as sourced records (one
pH-response case is bound to a SABIO-RK entry) and keeps their conditions
attached.

# Limitations and claims not made

- One organism, one substrate, one laboratory's data; no transfer to another
  strain, substrate or condition has been tested. A survey found no open
  raw-data deposit of a comparable submerged cellulose culture; figure
  digitisations with explicit digitisation uncertainty are the only
  candidates and need full-text review before use.
- Every error model is an assumption because the deposit holds no
  replicates; the noise multiplier absorbs model misfit and measurement
  noise together.
- Nutrient, oxygen and maintenance physiology are absent from the organism
  case; solid-substrate accessibility is a placeholder; there is no spatial
  mycelium.
- The least-squares optimiser's stopping rule is now known to stop above
  the minimum on this problem; the tightened rule and its re-run are
  pending.
- The stage B chains did not reach the declared convergence rule within the
  plan's compute cap; their verdicts are provisional.
- Software verification (parity tests, reference simulators, cross-solver
  agreement) is not empirical validation, and this paper makes no
  predictive biological claim.

# Reproducibility and availability

FungMod is MIT-licensed at https://github.com/felixlaga/FungMod with
documentation at https://fungmod.readthedocs.io/. Each study above has a
runner script, a frozen plan, a README and checksummed results; the
cross-solver reproduction runs in about 90 seconds with
`scripts/run_gelain_2020_petab_reproduction.py` and the `copasi` extra.
A pinned runtime lock file, a wheel build with an installed-wheel smoke test
outside the checkout, and `scripts/reproduce.py` for the headline
artifacts exist; extending the single command to every table in this paper
and archiving a tagged release with a DOI are *pending*.

# AI assistance disclosure

The code, studies and this draft were produced with substantial assistance
from an AI coding assistant (Claude Code, Anthropic) directed by the
author, under the repository's written rules on provenance, maturity
labels and forbidden shortcuts, with every scientific study run under a
plan frozen before its first fit. Human review of the biological mapping
and of this text is outstanding and is not claimed here.

# Acknowledgements

The Gelain et al. deposit (CC BY 4.0) made the organism case possible. The
COPASI, libSBML, PEtab and SciPy communities provided the tools the
cross-solver study depends on.

# References
