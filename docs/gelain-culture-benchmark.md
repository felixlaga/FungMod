# A bounded T. harzianum culture benchmark

This page and its recorded results preserve v1. The
[v2 joint comparison](gelain-joint-benchmark.md) now adds activity observations,
alternative mass/hydrolysis models, error assumptions and scoped validation.

FungMod now runs a reproducible **exploratory** whole-culture comparison for
*Trichoderma harzianum* P49P11. It reproduces the biomass/substrate projection of
the deposited Gelain model and tests a simpler effective growth/loss hypothesis
on six complete condition holdouts. The new model has substantial prediction
errors, especially on cellulose. This is a research benchmark, not independent
biological validation or a full fungal organism model.

## Run it

From an installed development checkout:

```sh
python scripts/prepare_public_experimental_data.py --check
python scripts/run_gelain_2020_culture_benchmark.py --output outputs/gelain-culture-benchmark
```

Use a new, empty output directory for each run. All inputs are already local;
no network access or MATLAB execution is required. `report.md` gives the main
table, `report.json` contains diagnostics and every optimizer start,
`residuals.csv` preserves signed residuals, and `holdouts.png`/`.svg` show the
predictions. Each fold writes a checksum-bound prediction before scoring its
held-out responses. `inputs.json` hashes the plan, sources, extracted data and
study code; `software.json` hashes the Python source tree and project configuration;
`artifacts.json` hashes every result. This protects traceability,
not blinding: the design is retrospective and source-informed.

The recorded run is preserved under `data/benchmarks/gelain_2020/results/`;
tests recheck artifact hashes and recompute its predictions and scores without
refitting. Plot byte hashes can vary on regeneration because graphics metadata
and font libraries differ; scientific reproducibility is checked numerically.
The fixed design is `data/benchmarks/gelain_2020/plan.json`. The implementation
is `fungal_model.research.gelain_culture`, separate from the generic engine and
the existing fungal-coupling API. No strain parameters are promoted to the
registry, and no existing numerical model changes.

## Source and observation mapping

The primary sources are the [Gelain et al. article](https://doi.org/10.1016/j.cesx.2020.100085)
and [Mendeley V2 archive](https://doi.org/10.17632/shd3wcczsr.2), licensed CC BY 4.0.
The source review checked Methods 2.2–2.4, Eqs 2–8, the deposited MATLAB/Simulink
formulas and the Information documents. It is a computational review; an
independent fungal physiologist has **not** approved the biological mapping.

| Record | Benchmark interpretation | Unresolved limitation |
| --- | --- | --- |
| Culture biomass, g/L | State X predicts dried pellet mass for glycerol, or total dry mass minus acid-treated residue for cellulose | Not a viable-biomass count; inactive/dead material, separation bias and correlated assay errors are unresolved |
| Remaining glycerol or cellulose, g/L | State S predicts the reported bulk substrate assay | Cellulose is insoluble bulk material, not dissolved uptake substrate; accessibility and hydrolysis are unresolved |
| t=0 entries | Fixed initialization, excluded from all fitting residuals | Inoculum variability is not known; source averages are not exact measurements |
| Source enzyme-producing state A | Latent proxy only in source reproduction | No direct observation and no equivalence to FungMod active biomass; not constrained to be a subset of X |
| FPU/L and U/L | Excluded from this benchmark | No justified conversion to enzyme mass/molarity; no inferred secretion dynamics |
| Duplicate means | Eight post-initial points per observable/condition | Individual runs, SD arrays, covariance and detection limits are unavailable |

The source cellulose initialization is 0.4 g/L in its simulations; new fits use
the workbook's 0.3990672957214788 g/L. Glycerol uses 0.5 g/L. Nominal initial
substrate is retained even when the early assay exceeds it. Recorded zeros,
reversals and the 54 h Methods discrepancy remain visible. No observations are
smoothed, imputed or silently dropped.

A follow-up search recovered the author's [2020 thesis](https://doi.org/10.4233/uuid:cf8840b6-c075-4e3e-af43-2b9fbc7ff0a1).
Printed page 25 describes dried pellet biomass for glycerol and acid treatment
of dried cellulose cultures. Page 28 explains biomass by mass difference and
possible incomplete digestion at high cellulose. These measurements can have
correlated errors; independent equal-variance assay noise is not established.
Page 38 says the 5/40 g/L cellulose assays were tried during estimation, gave
poor fits, then served as extrapolation cases. They therefore must not be
called blind source validation. Page 108 starts a code supplement referring to
the same fitting workbooks; it did not supply the missing replicate arrays.
The review's URL, file hash, page references and access results are recorded in
`data/benchmarks/gelain_2020/thesis_review.json`. The full thesis is not redistributed.

Scope is the reported medium and controlled stirred batch reactor: 29 °C,
pH 5.0 ± 0.5, oxygen maintained above 30%, and 0–96 h. Glycerol and cellulose
have separate parameter estimates; their inocula and physiology are not pooled.
Peptone and other medium components prevent interpreting the reduced model as
a measured whole-culture carbon/energy balance.

## Explicit models

In canonical units hours and g/L, the new effective hypothesis is:

```text
g = mu * S/(K + S) * X
dX/dt = g - kd*X
dS/dt = -g/Y
```

`mu` and `kd` have units 1/h, `K` has g/L and `Y` is an apparent g/g yield.
Every parameter is fitted, unit-checked and provenance-labelled. Its bounds
are explicit exploratory choices, not measured strain constants. Biomass loss
means loss of the measured pool; it is not an identified mortality mechanism.
Applying this law to cellulose is a deliberately reduced effective hypothesis,
not an assertion that fungi directly import insoluble cellulose. With `kd=0`,
the mathematical relation `S + X/Y = constant` is tested. With loss, that
quantity decreases by `kd*X/Y`; this is not a physical carbon closure claim.

For the source projection, `g = mu*S/(K+S)*(1-X/Xmax)*X`. Glycerol consumption
is `-alpha*g*X`; the additional factor X in Eq 2 is retained, with alpha in
L/g. Cellulose also has an induction term
`a = mue*S/(Ke+S)*(1-A/Amax)*X`, `dA/dt = a-kda*A`, and consumption
`-alpha*g*X-beta*a*A`. These source-specific formulas remain in the study module.
Activity equations do not feed back into X/S/A, so this projection can be
checked without pretending to reproduce all 21 source parameters/activities.

**Paper/code discrepancy:** Eq 5 writes glycerol death as `d*X`, while the
deposited Simulink code uses `d*S/(S+Kd)*X` with
`Kd = 1.0327710167947122e-13 g/L`. It is tiny but not equivalent to zero near
depletion. Separate `source_paper_v1` and `source_deposited_v1` implementations
make this explicit. At 20 g/L glycerol they differ by about **0.815 g/L biomass**
late in the run. Source parity uses the deposited formula and sufficiently
small substrate absolute tolerance. It does not silently change Eq 5.

The preserved `simulation_reference/*.xlsx` files and extracted
`source_simulations.csv` are **simulation outputs**, used only for software
parity. They are never imported into ExperimentDataset or fitted as data.
Published source constants were fitted to all six conditions: their empirical
scores are descriptive comparisons, not held-out predictions.

## Fitting and checks

For each substrate, two complete conditions train four parameters; the third
condition is predicted. No random time-point split is used. The primary loss
scales each observable by its maximum in the training conditions. A prespecified
sensitivity run gives equal weight to residuals expressed in g/L. These are
loss weights, **not SD estimates**. There is no chi-square, likelihood, confidence
interval or biological pass threshold. Source-fitted parameters do not fix or
initialize the new fits.

The plan fixes four log-space starts, seed 1729, bounds, a 300-evaluation cap
per start and finite-difference step. A training-only numerical pilot motivated
the explicit derivative step; no held-out scores were evaluated in that pilot.
Every attempted start and failure is retained. Selection uses only the training
loss. All-start failure stops the run. Jacobian rank/conditioning and bound
contact describe the chosen objective and do not establish identifiability.
Two additional all-condition fits are labelled calibration only.

Unit and provenance failures, invalid inputs, failed/incomplete/nonfinite
integrations and materially negative states raise errors. Only trial RHS
evaluations floor negative solver iterates; returned states are not clipped.
Small negative numerical roundoff is recorded. Every held-out prediction is
checked against DOP853 and a tighter LSODA run. The 1e-5 g/L agreement criterion
is numerical, not biological. Independent tests cover analytical loss,
zero-substrate behavior, apparent-yield conservation, units, source parity,
artificial parameter recovery, source checksums and holdout response isolation.

## Observed benchmark result

The 2026-09-28 run produced the following **primary holdout RMSE**, in g/L:

| Held-out condition | Biomass | Substrate |
| --- | ---: | ---: |
| Glycerol 5 g/L | 1.0555 | 0.8983 |
| Glycerol 10 g/L | 0.8726 | 1.3482 |
| Glycerol 20 g/L | 2.2948 | 1.4924 |
| Cellulose 10 g/L | 1.8848 | 1.0864 |
| Cellulose 20 g/L | 1.6140 | 2.8314 |
| Cellulose 30 g/L | 2.4796 | 7.4446 |

Each observable improves over a constant-initial-state comparator, a weak
baseline. That does not make the errors biologically acceptable. The model
misses early lag, some biomass peaks, late biomass persistence and cellulose
consumption tails. At 30 g/L cellulose, equal-g/L weighting changes substrate
RMSE to **3.4869**, while biomass RMSE worsens to **2.8906**. This dependence on
the error assumptions is material; neither weighting is selected post hoc.

All six source trajectories reproduce within **9.19e-7 g/L**. Maximum differences
are **2.06e-6 g/L** between solvers and **2.02e-6 g/L** under tolerance refinement.
Two of 56 starts hit the evaluation limit, both in the primary glycerol 20 g/L
holdout fit; that fold's other two starts succeeded. No selected fit contacts
the declared bounds. Full numerical Jacobian rank does not resolve uncertainty
or model discrepancy.

## Next evidence, before more biology

Recover raw duplicate trajectories, SD definitions, detection limits and the
source extrapolation/validation conditions (15 g/L glycerol and 5/40 g/L cellulose).
Review the recovered separation protocol with a domain researcher. The search has not
recovered those numeric arrays. Source plots may support separately labelled
digitization, but cannot recover true replicate runs. No author was contacted.

Have a domain researcher review the observation mapping and the largest
residuals. Compare predeclared lag/loss and hydrolysis hypotheses using new
matched evidence, retaining this benchmark unchanged as the first baseline.
These six conditions have now informed model criticism and must not be called
blind validation for the next model. Independent measurements and an error
model remain prerequisites for transferable biological claims. See the
[paper-readiness roadmap](paper-readiness.md).
