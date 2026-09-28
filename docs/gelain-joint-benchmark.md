# Joint culture, activity and biomass comparison

This extends the preserved [v1 benchmark](gelain-culture-benchmark.md) with all
144 non-initial observations from the six Gelain culture conditions. It
implements the five proposed development steps: richer model comparison,
activity observations, retained dry mass, explicit error models and diagnostics,
and validation records bound to an exact model. It does **not** convert a
retrospective fit into independently validated biology.

## Reproduce the comparison

```sh
python scripts/prepare_public_experimental_data.py --check
python scripts/run_gelain_2020_joint_benchmark.py --output outputs/gelain-joint --workers 3
```

Use an empty output directory. The runner operates offline, checks the original
source hashes, and refuses to complete if its inputs or implementation change
while it runs. `data/benchmarks/gelain_2020_v2/plan.json` specifies bounds, starts,
losses, solvers and development screens. `results/` preserves the recorded run.
No published all-condition parameter estimate initializes or fixes a free
parameter in a training fit. Source parameter reproduction is a separate task.

There are 33 whole-condition holdouts, 11 descriptive all-condition fits, and
132 optimizer starts. Glycerol uses three models and one fitting loss; cellulose
uses four models and two loss scenarios. Within a family, each fold trains on
exactly two conditions, keeping all eight post-initial time points of the third
condition together. Loss normalizers come from training responses only.
The study design is retrospective after v1 residual inspection and informed by
this publication; it is neither blinded nor independent validation.

Outputs include frozen predictions before scoring, signed residuals, pooled
scores in original assay units, model/parameter provenance, all successful and
failed starts, rank/bound diagnostics, nuisance-reoptimized profile losses,
conditional bootstrap draws, source reproduction differences and holdout plots.
Input, implementation and result manifests carry SHA-256 hashes. Runtime
versions, the Python version and direct dependency pins are recorded.

## The implemented alternatives

| Family | Model | Free parameters | Observation and mechanism |
| --- | --- | ---: | --- |
| Glycerol | Effective | 4 | Monod growth, apparent yield and biomass loss; observed dry mass = X |
| Glycerol | Published | 5 | Source Eqs 2–5, including the published extra X factor in substrate consumption and constant death term |
| Glycerol | Retained | 6 | Effective model plus retained dry mass R; measured mass = X + R |
| Cellulose | Effective | 8 | Effective mass dynamics plus constitutive production and loss of both assay activities |
| Cellulose | Published | 20 | Source mass, induction and two activity equations, including substrate-dependent inhibition switches |
| Cellulose | Hydrolysis | 9 | Consumption driven by measured filter-paper activity, substrate saturation and induced activity production |
| Cellulose | Hydrolysis with retention | 11 | Hydrolysis candidate plus retained dry mass |

The source is [Gelain et al., Eqs 2–10](https://doi.org/10.1016/j.cesx.2020.100085)
and its [deposited archive](https://doi.org/10.17632/shd3wcczsr.2). The published
cellulose model contains an exact scale ambiguity in its unmeasured A state.
The coordinate change z = A/Amax removes one redundant scale: k_ind = μe/Amax,
b_ind = β Amax², and the activity production coefficients absorb Amax. The
inhibition constants absorb the source's manually selected 0.15 coefficient.
All remaining coefficients are fitted afresh. These are algebraic changes,
not new measurements of the latent state. The separate v1 reproduction keeps
the glycerol paper/deposited-code discrepancy documented and unchanged.

The hydrolysis hypothesis uses consumption = k_h F S/(Kh + S), growth = Y ×
consumption, and activity production proportional to X S/(K_ind + S). F is
filter-paper assay activity. Its fitted coefficient k_h is preparation-specific;
it is **not** a conversion of assay activity into enzyme concentration or a
universal cellulose rate constant. β-glucosidase activity is fitted as a separate
response and has no unsupported direct feedback into the bulk-consumption law.
Soluble intermediates, co-substrate consumption, accessibility and transport
remain unresolved. These explicit hypotheses must earn support from data.

The retained-mass hypothesis uses R' = f_retained kd X − k_clear R and observes
X + R. Initial retained mass is explicitly fixed to zero for this comparison,
with its assumption recorded. These are growth-associated and retained dry-mass
pools, **not** verified living/dead biomass. No viable-cell output is emitted.

## Activities and measurement errors

Original workbook cells, units, initial conditions and sources accompany each
value in `observations.json`. Initial values are excluded from fitting.
Filter-paper FPU/L and pNPG β-glucosidase U/L use distinct Pint dimensions
(`gelain_fpu/liter` and `gelain_beta_u/liter`); neither converts to mass,
molarity or the other assay. Import the study model module to register them.

The public workbook contains means without replicate identities or SD arrays.
The primary objective therefore uses training-maximum normalization as a
**descriptive weight**, never a measurement SD. The separate covariance
sensitivity declares SD = 10% of each training maximum and correlation
ρ(X,S) = −0.5. The negative sign is motivated by the cellulose mass-difference
assay; neither its magnitude nor the noise scale is measured. Errors across
times are assumed independent. The sensitivity cannot establish a confidence
interval or turn a failed primary model into an accepted biological model.

`GaussianObservationError` also accepts explicitly sourced SD/SE, simultaneous
covariance, and known left-censoring limits. SD/SE must describe the supplied
observations; replicate SD is not silently converted to an error on a mean.
One censored response per simultaneous row is supported through the exact
conditional Gaussian CDF; multiple correlated censored responses fail explicitly.
Recorded zeros are ordinary measurements unless a sourced detection limit is
provided. The Gelain run invents no detection limits and applies no censoring.

Three optimizer starts, local Jacobian singular values, parameter tradeoffs,
bound contacts and fixed-parameter nuisance refits expose weak constraints.
Nuisance refits restore the fitted observation-error and censoring model exactly;
changing to descriptive weights during a profile is prevented by regression tests.
Full local rank is not proof of global identifiability. Profile grids at half,
original and double the fitted value are bounded diagnostics, not exhaustive
confidence regions; improvements over the reference fit remain visible.
The 20-draw parametric bootstrap uses assumed errors and reports failures.
Bands require at least 12 converged draws and describe conditional parameter
variation at the supplied designs. They omit new measurement noise and are
neither empirical confidence intervals nor validated prediction intervals.
Synthetic bootstrap draws never enter the experimental-data library.

## Model selection and numerical checks

A more complex candidate must improve the mean normalized held-condition MSE
by at least 10% against the effective null, worsen no individual observable's
normalized MSE by more than 10%, and have full practical local rank in every
fold and the all-condition fit. These thresholds are development screens,
not scientifically established acceptance tolerances. Model selection itself
uses the holdout results, so an independent test remains necessary.

Every successful fold checks LSODA against DOP853 and tighter LSODA tolerances,
with a maximum training-scale-normalized difference of 1e-5. Source fixed-step
activity trajectories differ from accurate integration near inhibition switches;
the recorded activity differences are retained, not presented as exact parity.
The X/S projection is separately tested against the preserved implementation.
The published activity equations also have analytic decay-limit tests.

## Recorded result (2026-09-28)

The published equations give the lowest primary held-condition error for both
families. All 33 folds pass both numerical checks; the largest scaled solver
difference is 2.25e-7. Six of 132 optimization starts fail and remain recorded.

| Family / model | Biomass RMSE (g/L) | Substrate RMSE (g/L) | FPU/L RMSE | pNPG U/L RMSE |
| --- | ---: | ---: | ---: | ---: |
| Glycerol / effective | 1.544 | 1.272 | — | — |
| Glycerol / published | 0.458 | 1.005 | — | — |
| Glycerol / retained | 1.458 | 1.226 | — | — |
| Cellulose / effective | 2.231 | 2.883 | 394.0 | 834.9 |
| Cellulose / published | 0.762 | 1.162 | 83.8 | 149.7 |
| Cellulose / hydrolysis | 2.493 | 2.465 | 346.9 | 726.7 |
| Cellulose / hydrolysis with retention | 2.489 | 2.487 | 350.1 | 733.5 |

These are pooled errors across three complete held-out conditions per family,
with each fit's parameters estimated without its held-out responses. They are
retrospective development results, not independent accuracy estimates.

For the previously problematic 30 g/L cellulose condition, substrate RMSE falls
from v1's 7.4446 to 1.6207 g/L. At 24 h the published-model refit predicts
16.9647 g/L, versus 15.7340 measured and v1's 0.0671 prediction. This comparison
also adds activity measurements and model parameters; it does not isolate a
single mechanism's causal contribution.

The published glycerol model passes the defined complexity screen. The
published cellulose model fails it because one primary training fold has
practical rank 19/20. Its profile refits also improve the descriptive full-fit
objective from 0.19135 to 0.18980, warning that the original fit is not a proven
global optimum. Neither result is concealed by choosing a new best fit after
scoring. Both hydrolysis candidates fail the primary observable-worsening
screen. Their different outcome under assumed covariance is sensitivity to an
unverified noise model, not independent support. Retained mass offers only a
modest improvement over the glycerol effective null and is less accurate than
the simpler published glycerol equations.

All profile points converge and both conditional bootstraps complete 20/20
refits. This verifies that the procedures run; it does not validate their
assumed noise or empirical coverage. Source activity-reproduction discrepancies
reach about 22.34 FPU/L and 19.65 pNPG U/L, while source biomass/substrate agree
within 3e-9 g/L in this comparison. Exact activity parity is not claimed.

## Validation tied to a model and operating scope

Each successful all-condition fit gets a readiness packet binding implementation
hashes, parameter values and provenance, observation law, training identities,
strain, substrate, medium, reactor, temperature, pH, initial substrate range,
and observation-time interval. A proposed operating range is not a validated
range. Current packets remain `awaiting_evidence`.

The reusable `fungmod.calibration` APIs `model_identity`, `ModelScope`,
`freeze_scoped_prediction` and `evaluate_scoped_prediction` bind exact model
parameters, observation mappings and acceptance thresholds before evaluation.
The evaluator checks hashes, independence from training identities, scope,
actual observation times, units and raw-replicate evidence through the existing
[independent-validation workflow](independent-validation.md). Synthetic tests
cannot generate empirical validation status. Passing empirical criteria applies
only to supplied tested conditions; it does not validate every point in a
range, authenticate human review or authorize a publication claim.

For this dataset, individual replicates, measured uncertainty, matched independent
experiments, predeclared biological acceptance criteria and independent domain
review remain unavailable. The next empirical task is to obtain those inputs
and test frozen predictions. For cellulose, first reduce or constrain the
published model's unsupported parameters and preregister a new comparison.
Changing a maturity label alone cannot supply the missing evidence.
