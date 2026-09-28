# Experimental data and the path to a paper

Assessment date: 2026-09-28. FungMod is usable for bounded exploratory research
and software-method development. It is not yet a validated general predictor
of fungal degradation. A useful software paper is achievable without modelling
every part of a fungus, provided its demonstrated scope and claims match.

## Data now available

The public-data intake is in `data/experiments/source_intake/`, with original
files, licenses, download URLs and SHA-256 digests. The offline extractor is
`scripts/prepare_public_experimental_data.py --check`.

| Source | Fetched and checked | Permitted use | Missing evidence |
| --- | --- | --- | --- |
| [Gelain 2020](https://data.mendeley.com/datasets/shd3wcczsr/2) | Original archive, article, six experiment workbooks, source classification notes; 162 recorded entries including 18 initial conditions | Reproducible exploratory culture benchmark, source-model projection and six condition holdouts | Individual duplicates, SD arrays, human review of the explicit provisional mapping, source validation-condition observations |
| [Novy 2021](https://doi.org/10.6084/m9.figshare.14490032.v1) | Original secretome workbook, repository metadata, 232 populated protein rows extracted | Select candidate enzyme classes and compare endpoint composition for T. reesei QM6a | Absolute abundance, secretion time courses, kinetic rates, matched replicate columns |

Gelain uses *T. harzianum* P49P11, with three glycerol and three cellulose
conditions. The curated library now includes 96 non-initial biomass/substrate
observations. The [joint benchmark](gelain-joint-benchmark.md) uses all 144
non-initial biomass, substrate and assay-activity observations; the 18 initial
entries remain separate. This is much more useful for a fungal-growth benchmark than
another isolated-enzyme digitization. It still does not pass the
[independent-validation](independent-validation.md) raw-replicate requirements.

The archive's files named `data.xlsx` are explicitly **simulations**, as explained
by its Information documents. They are excluded from observations and now used
separately as software reproduction references. The source's claimed
validation conditions are absent as observation workbooks. All six fetched
conditions were used in the original paper's parameter estimation. Any new
leave-one-condition-out test is a retrospective, within-study assessment; it
cannot be presented as a blinded or independent laboratory validation.
The subsequently recovered thesis also says the 5/40 g/L cellulose conditions
were tried during estimation before being used for extrapolation. Their source
selection history precludes calling them blind validation if later digitized.

The source workbooks lack replicate errors. FPU/L and U/L are assay activities,
not enzyme concentrations. The 54 h sampling entries conflict with the Methods
sampling list and are retained with that discrepancy recorded. No unknowns are
filled with guessed constants. Existing enzyme datasets retain their previous
digitization, preparation and identifiability limitations.

## What must be finished for a strong software paper

1. **Fix the claim and comparison.** Demonstrate provenance-aware virtual
   experiments, reproducible calibration and honest limits for named supported
   systems. Explain the gap relative to existing ODE/SBML tools and metabolic
   modelling packages. “Full fungal prediction” is outside the evidenced scope.
2. **Strengthen the first reproducible empirical benchmark.** The
   [Gelain culture benchmark](gelain-culture-benchmark.md) now reproduces the
   source X/S/A projection. Its [v2 extension](gelain-joint-benchmark.md)
   refits the published equations and compares activity-driven hydrolysis and
   retained dry-mass hypotheses on whole-condition holdouts. Activity assays
   now constrain model outputs, while assay units, unknown errors, covariance
   assumptions and source numerical discrepancies remain explicit. Parameter
   support and independent predictive performance still need evidence.
   Accessibility, uptake, co-substrates and transport remain unresolved.
   No strain-specific core branch was added.
3. **Quantify what the data identify.** Use multiple starts, profile likelihood,
   residual structure and parameter sensitivity. Specify the error model and
   distinguish measurement noise from between-culture variation and model
   discrepancy. Without recovered SD/replicates, use clearly labelled exploratory
   fits and sensitivity to error assumptions, not empirical confidence claims.
4. **Test predictions with a frozen analysis.** Choose complete conditions/runs
   as holdouts rather than random time points. Predeclare observables and
   acceptance tolerances, freeze fitting/model-selection choices, then score
   without refitting. Obtain an independent matched dataset or a new experiment
   for claims of transferable biological prediction. Report failed predictions.
5. **Complete release verification.** Run the full quality gates on the final
   commit; obtain green hosted CI; prove clean installation and offline execution
   from the built wheel; independently reproduce a benchmark with another solver.
   Record conservation, nonnegativity, tolerance convergence, parameter bounds,
   missing values and solver failures. The earlier local suite and standards
   fixes are a strong base, but do not establish a biological validation result.
6. **Make the research result citable and usable.** Supply one command that
   recreates paper tables/figures, a pinned environment, data manifest, explicit
   model versions and seeds, a tagged archived release/DOI, complete citation
   metadata, a short manuscript, and a successful independent user walkthrough.
   Document real research use and have a domain researcher review the biological
   interpretation. Human review is still outstanding; it cannot be asserted by
   this automated intake.

A software paper and a biological validation paper have different claims.
Independent wet-lab validation is necessary for the proposed predictive biology
claims, not a universal admission requirement for every software publication.

### Venue timing

The current [JOSS submission rules](https://joss.readthedocs.io/en/latest/submitting.html)
require research use, sustained open development and more than six months of
public history. Its [review criteria](https://joss.readthedocs.io/en/latest/review_criteria.html)
also examine installation, functionality, tests, documentation and comparison to
existing tools. AI assistance must be disclosed with genuine human review; do
not manufacture that review or authorship evidence.

GitHub reports this repository was created on **2026-05-25** and is public now.
Creation does not establish when it became public. If it was public from
creation, **late November 2026 is the earliest plausible JOSS history window**;
later public availability moves it later. Meeting that window does not guarantee
eligibility or acceptance. These are JOSS-specific rules, not a definition of
scientific validity or a restriction on preparing a methods paper/preprint.

## When can FungMod model a full fungus?

| Target | Current position | Required next evidence |
| --- | --- | --- |
| Extracellular enzyme degradation | Implemented for bounded named mechanisms; exploratory comparisons exist | Matched conditions, identified parameters, uncertainty, held-out predictions |
| One strain in a controlled reactor | Minimal coupling plus a separate data-backed effective biomass/substrate benchmark with source reproduction and retrospective holdouts | Resolve model discrepancy and observation mapping; explicit induction/production, suitable activity measurements and independent predictions |
| Physiologically constrained strain model | Not implemented as a coupled organism model | Transport, oxygen transfer and respiration, carbon/nitrogen/energy balances, intracellular metabolic coupling, secretion allocation and regulation |
| Spatial filamentous colony | Fixed-grid reaction diffusion exists; moving fungal morphology does not | Hyphal extension/branching, local uptake/secretion, diffusion and boundary coupling, substrate accessibility, microscopy and spatial validation |
| Arbitrary fungus on arbitrary material | Unsupported | Multiple validated strain/substrate/environment models and demonstrated transfer; genome annotations alone cannot supply kinetics |

The existing coupling's “active biomass” and the source paper's induced
enzyme-producing biomass must not be equated merely because both use the word
active. Growth, secretion and uptake abstractions need a reviewed biological
mapping before calibration. Likewise, measured dry biomass may include inactive
or dead material and cannot automatically be mapped to viable biomass alone.

For the first bounded culture case, model oxygen as nonlimiting only within the
reported controlled conditions and state that restriction. Coupled oxygen
dynamics and respiration are required before predicting oxygen limitation or
scale-up. They are not necessary prerequisites for every limited first paper.

For intracellular metabolism, reuse a suitable strain-specific reconstruction
where available and couple it to extracellular dynamics through explicit
exchange fluxes. [Yeast9](https://doi.org/10.1038/s44320-024-00060-7) illustrates
how substantial an existing fungal metabolic model already is. Its scope is
metabolism; it is not a complete dynamic filamentous colony and cannot simply
be transferred to a different species. Genome-scale does not mean whole-organism.

**Work can start on the first data-backed whole-culture model now.** My planning
estimate is several focused development weeks for a reproducible exploratory
case, assuming the source ambiguities can be resolved. Predictive validation
depends on independent experiments and is more realistically a months-scale
effort with a domain/lab collaborator. These are effort estimates, not evidence
of readiness or delivery promises. A comprehensive regulated, spatial fungal
digital twin is a multi-year research programme with no defensible completion
date from the current project evidence.

Recommended next task: retain the completed Gelain benchmark as a baseline,
recover duplicate trajectories and the omitted validation-condition observations,
and obtain a domain review of biomass loss and cellulose hydrolysis/uptake
mapping. Then predeclare the next model comparison against matched new evidence.
The current six conditions have informed model criticism and are no longer
blind validation for subsequent changes. Do not expand species or mechanisms
until this case makes useful, measurable predictions with recorded limitations.
