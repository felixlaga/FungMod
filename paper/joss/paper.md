---
title: 'FungMod: provenance-aware virtual experiments for fungal and enzymatic substrate degradation'
tags:
  - Python
  - mycology
  - enzyme kinetics
  - mechanistic modelling
  - provenance
  - reproducibility
authors:
  - name: Felix Laga
    orcid: 0009-0008-8141-8172
    affiliation: 1
affiliations:
  - name: KU Leuven, Leuven, Belgium
    index: 1
date: 6 October 2026
bibliography: paper.bib
---

<!--
Draft for a JOSS submission (2026 paper format: Summary, Statement of need,
State of the field, Software design, Research impact statement, AI usage
disclosure). Items in square brackets marked "Author" must be completed or
confirmed by the author before submission; they are deliberately visible.
-->

# Summary

Fungi and the enzymes they secrete break down cellulose and other solid
substrates, and how fast they do so depends on the organism, its enzymes, the
substrate and the conditions. FungMod is a Python package for asking that
question as a virtual experiment: the user names a fungus or enzyme source, a
substrate and a set of conditions (for example a grid of temperature and pH),
and FungMod assembles a mechanistic model and simulates substrate loss,
product release, degradation rate and the time to reach given degradation
thresholds, with uncertainty intervals. Every result carries the source and
maturity of each input, the assumptions made, the inputs that are still
unknown and the measurements that would supply them. The model is assembled
from records (organisms, enzyme classes, substrates, environments and
parameters) rather than from code written for one organism, so the same
workflow runs on the shipped records, on a user's own records, and on records
built from the user's data or from public kinetic databases. The assembled
models can be calibrated to measured time courses and exported to the
community standards SBML, SED-ML, COMBINE and PEtab.

# Statement of need

Models of fungal and enzymatic degradation are usually published as equation
sets fitted to one dataset [@kadam2004; @gelain2020], with the units, the
origin of each constant and the error model left implicit. Reusing such a
model for another strain, substrate or condition means re-deriving all three,
and a researcher who wants to compare several organisms, substrates or
conditions before running experiments has no tool that composes the model
from what is known and states what is not. FungMod is written for that
researcher: experimental mycologists, bioprocess and enzyme engineers who
plan or interpret degradation experiments, and modellers who want such
models in a form other tools can read. It supplies three things together.
First, composition: a model is built from declared records by matching the
enzyme classes of a source to the substrate and its bond classes through
declared process-compatibility records. Second, honesty about evidence: an
unknown input stays unknown, so a case with a missing constant is reported as
underparameterised with the missing items listed, and exploratory
assumptions run only on explicit request and are labelled in every output.
Third, data in and out: user time courses and kinetic constants enter through
documented schemas, calibration and posterior sampling run on the same
models, and the models leave through the standards.

# State of the field

General systems-biology software solves the simulation and estimation of a
model that the user has already written. COPASI [@hoops2006] and Tellurium
[@choi2018] simulate and analyse reaction models; PEtab [@schmiester2021]
specifies estimation problems that tools such as pyPESTO [@schaelte2023]
solve; SBML [@hucka2003], SED-ML [@waltemath2011] and COMBINE archives
[@bergmann2014] exchange models and simulation set-ups. None of them composes
a degradation model from an organism, a substrate and a condition, carries
assay-defined enzyme activities (such as filter-paper units) that cannot be
converted to molar amounts, or refuses to report an output that its inputs
do not support. Constraint-based tools such as COBRApy [@ebrahim2013] model
intracellular metabolic flux at steady state, not extracellular degradation
over time. Enzyme resources such as BRENDA [@chang2021], SABIO-RK
[@wittig2012] and CAZy [@drula2022] hold kinetic constants and family
classifications but do not simulate. Continuum models of mycelial growth
[@edelstein1982; @boswell2003] are usually implemented for one study.

We built FungMod rather than extending one of these tools because its new
parts, the record registry, the evidence gating and the provenance carried
into every output, concern biological bookkeeping, not numerics, and have no
natural place in a general simulator. Where the general tools are strong,
FungMod contributes to them instead of replacing them: its models export to
SBML and PEtab so that COPASI and PEtab-based estimators can simulate and fit
them, and the repository includes a check that re-runs an exported
estimation problem in COPASI and compares it with FungMod.

# Software design

**Records and assembly.** Each parameter record holds a value of one of five
kinds (exact, range, distribution, unknown, not applicable), a unit, a source
and a maturity label, and declares which uses it allows. A preflight matches
the requested source, substrate and environment, selects a case template and
assembles the process laws through one of five assemblers (surface
catalysis, homogeneous Michaelis-Menten, pH-ionised Michaelis-Menten, culture
physiology and an extracellular enzyme chain). Nothing is inferred from an
organism's name. The trade-off is coverage: a fungus without records yields a
list of missing parameters and suggested measurements, not a guess.

**Modes.** An exploratory mode accepts labelled exploratory priors; a
scientific mode refuses to run unless every input is sourced and valid, and
says that this does not mean experimentally validated. Both modes write
versioned tables (time series, final metrics, threshold times, uncertainty,
conservation, solver and thermodynamic diagnostics, provenance, limitations,
missing parameters, suggested experiments) and a manifest.

**Numerics.** Process laws compile to array kernels with units resolved once
at build time using Pint; SciPy [@virtanen2020] integrates them. Uncertainty
is propagated by sampling the declared ranges and distributions, with local
and variance-based sensitivity.

**Calibration and evidence.** Least squares with profile likelihood and an
affine-invariant ensemble sampler [@goodman2010] classify which constants a
dataset identifies. Studies run under plans frozen by SHA-256 digest before
any fit, and every recorded result cites the digest of its plan.

**Data intake.** A SABIO-RK client fetches kinetic-law entries on request,
stores them as digested snapshots and turns them into proposals that must be
reviewed and signed before they become registry records; fetched values never
flow into a simulation directly. A genome route maps dbCAN CAZyme
annotations to enzyme classes through a curated CAZy family map; it reports
which classes are present but never assigns a rate, and it is not yet
connected to virtual experiments.

**Spatial mycelium.** An exploratory module simulates hyphal and tip
densities with tip extension, branching, anastomosis, uptake and
translocation [@edelstein1982; @boswell2003] on conservative finite-volume
grids (one to three Cartesian dimensions, or axisymmetric), with sparse or
banded Jacobians. It is verified against analytic front speeds,
conservation, symmetry and solver agreement, carries no organism parameters
and is not yet connected to the registry.

# Research impact statement

FungMod 0.1.1 is released on PyPI under the MIT licence, with documentation
at https://fungmod.readthedocs.io/. About 2,000 automated tests run on Linux,
macOS and Windows for Python 3.11 to 3.13. The repository includes four
reproducible case studies on the published *Trichoderma harzianum* P49P11
cellulose cultures [@gelain2020] (holdout benchmarks, posterior sampling,
preregistered model comparison and cross-solver reproduction in COPASI), each
with a frozen plan, a runner script and checksummed results, and one command
regenerates every table and figure from those results. The registry is
deliberately small: one calibrated whole organism, two enzyme-level cases
sourced from SABIO-RK (one with a pH response), and labelled development
records.
[Author: add any realised use, such as groups or projects using FungMod,
talks, teaching or citations. If there is none yet, keep this paragraph as
the evidence of near-term significance and do not claim more.]

# AI usage disclosure

The source code, tests and documentation of FungMod, and the first draft of
this paper, were written predominantly by an AI coding agent (Claude Code,
Anthropic) working under the author's direction. [Author: confirm and make
specific. For example: the author defined the scientific scope and the
central goal, wrote or approved the repository's rules on provenance,
maturity labels and forbidden shortcuts, chose and obtained the datasets and
checked their licences, decided the design trade-offs described above, and
reviewed the following parts of the code and text: ...] Correctness is
checked independently of the generating agent by the automated test suite on
three operating systems, by reference simulators and analytic solutions for
the numerical core, by re-running an exported estimation problem in COPASI,
and by frozen plans that fix every study's rules before its first fit.

# Acknowledgements

We thank the authors of the deposited *T. harzianum* culture data
[@gelain2020], released under CC BY 4.0, and the developers of COPASI,
libSBML, PEtab, SciPy and Pint, on which the package and its checks depend.

# References
