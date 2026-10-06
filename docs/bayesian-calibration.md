# Bayesian calibration and identifiability

FungMod can sample the posterior of a configured or registry case on the
compiled core, with explicit priors and an explicit Gaussian observation-error
model, and report which parameters the data identify and which the model must
keep as ranges. It cannot invent a noise level, prove global identifiability
from a finite chain, or turn a retrospective fit into validation; every result
carries the thresholds it used and a claim boundary saying so.

## What the machinery is

`fungal_model.calibration.bayesian` provides:

- **Priors.** `PriorSpecification` is `log_uniform` (uniform in the natural
  logarithm between positive bounds) or `uniform`, with unit-bearing bounds and
  a mandatory source. `NoiseScalePrior` is a log-uniform multiplier on the
  supplied standard deviations of one observable, or of a declared group of
  observables sharing one multiplier, sampled jointly with the parameters when
  the measurement error is unknown; the result labels it
  `estimated_from_residuals` because it absorbs model misfit together with
  measurement noise. A shared multiplier sets the overall error level while
  keeping the declared relative weighting of the observables; per-observable
  multipliers let the sampler re-weight the observables against each other.
- **Data.** `ObservedCondition` holds the rows of one condition in the units
  and order of its `GaussianObservationError`. Repeated times are replicates;
  `pooled_replicate_standard_deviation` turns within-time replicate scatter
  into a `measured_standard_deviation` error model.
- **Likelihood.** `build_bayesian_problem` combines priors, conditions and a
  prediction function `predict(parameters, condition_id, times)` into a log
  posterior in sampled coordinates. Prediction failures (an integration that
  does not complete, a shape mismatch) give `-inf`, are counted, and never
  silently replaced.
- **Sampler.** `run_ensemble_sampler` is the affine-invariant stretch move of
  Goodman and Weare (2010), updating each half of the ensemble against the
  other, gradient-free, with a pluggable `map_function` for process pools and
  checkpoint callbacks. `EnsembleRun.extend` joins resumed runs exactly.
- **Diagnostics.** Integrated autocorrelation time per coordinate with the
  automated window of Sokal as used by emcee, effective sample sizes,
  acceptance fractions and a declared convergence rule (chain longer than
  `autocorrelation_tolerance` times every tau, every effective sample size
  at least `minimum_effective_samples`). An unconverged chain is reported as
  such and its verdicts are marked provisional.
- **Identifiability verdicts.** `classify_identifiability` compares the
  credible interval of each parameter with its prior box in the sampled
  coordinate, using the declared `IdentifiabilityCriteria`:

| Class | Meaning |
| --- | --- |
| `identified` | interval width at most `identified_max_width_fraction` of the prior width, no bound contact |
| `weakly_identified` | width at most `weak_max_width_fraction`, no bound contact |
| `bounded_above_only` | the interval touches the lower prior bound: the data give an upper limit only |
| `bounded_below_only` | the interval touches the upper prior bound: the data give a lower limit only |
| `prior_dominated` | the interval touches both bounds or is wider than `weak_max_width_fraction` of the prior |

  The default criteria (`DEFAULT_IDENTIFIABILITY_CRITERIA`: one quarter, three
  quarters and two percent bound contact) are analysis conventions recorded in
  every result, not statistical tests. `parameters_left_as_ranges()` lists the
  credible intervals of everything not identified.
- **Local information.** `local_information_analysis` builds the Fisher
  information of the whitened residuals by central differences at the best
  posterior sample and reports its eigenvalues, practical rank and the least
  constrained parameter combination. It is a local curvature diagnostic, not a
  global proof.
- **Posterior predictive.** `posterior_predictive` gives quantile bands of the
  model prediction over posterior draws at requested times, optionally adding
  the (scaled) measurement error for bands on new observations.

`fungal_model.calibration.compiled_predictor` supplies the prediction function
for configured models: `ConfiguredConditionPredictor` rebuilds the condition's
`ModelConfig` through a factory for every candidate, loads its inputs,
assembles, compiles and integrates it at the observation times, and converts
the declared state to the observable's units. `inline_parameter_config_factory`
substitutes values into a config's inline parameters;
`fungal_model.screening.registry_case_config_factory` rebuilds a registry case
from its resolved records so that an overridden symbol reaches every place the
template binds it, including product-map coefficients derived from it.

Jacobians are not part of this step: the compiled core integrates with the
backend's finite-difference Jacobians unless a run opts into the compiled
state Jacobian ([compiled core](compiled-core.md)), no parameter sensitivities
are computed, the sampler is gradient-free, and the local information uses
finite differences of the residuals.

## The recorded study: T. harzianum P49P11 on cellulose

`data/benchmarks/gelain_2020_bayesian/` samples the nine hydrolysis-candidate
constants of the registry case `trichoderma_harzianum_p49p11` x
`cellulose_celufloc_200` jointly over the three Gelain 2020 cellulose loadings
(96 duplicate-mean observations of biomass, cellulose, filter-paper and
beta-glucosidase activity). The priors are the v2 joint-benchmark bounds,
log-uniform. The error model is the v2 `correlated_assumption` scenario
(standard deviation 10 percent of each observable's training maximum,
biomass/substrate correlation -0.5, independent in time, evidence `assumed`)
with one log-uniform scale multiplier shared by the four observables and
sampled with the parameters, because the deposit holds no replicates or
standard deviations. The shared multiplier sets the overall error level from
the residuals and keeps the declared relative weighting, so the posterior is
centred where the least-squares fit is and widened to the misfit actually
present. Run `python scripts/run_gelain_2020_bayesian_calibration.py --output
outputs/gelain-bayesian --processes 4` from the repository after
installation; the run checkpoints and resumes. A per-observable sensitivity
variant (`plan_per_observable_scales.json`, `--plan`, results in
`results_per_observable_scales/`) is recorded alongside it; see below.

## Results of the primary study

Chain: 24 walkers x 24000 steps, burn-in 4000 (20000 post-burn-in steps), mean
acceptance 0.32, integrated autocorrelation times 227 to 339 steps, effective
sample sizes 1414 to 2119; converged by the declared rule (every estimate from
a chain longer than 50 tau, every effective sample size at least 100). Of
576024 likelihood evaluations, 159794 had a non-finite log posterior, almost
all of them proposals outside the prior box, which the three constants pinned
at a bound make frequent.

| Symbol | Class | Posterior median | 95 percent credible interval | Prior box | Units | Point value inside |
| --- | --- | --- | --- | --- | --- | --- |
| `k_h` | `identified` | 0.0185 | [0.00714, 0.0639] | [1e-06, 1] | gram / filter_paper_unit / hour | yes |
| `Kh` | `bounded_below_only` | 18.4 | [4.26, 81.9] | [0.001, 100] | gram / liter | yes |
| `Y` | `identified` | 0.478 | [0.328, 0.648] | [0.01, 1] | dimensionless | yes |
| `kd` | `identified` | 0.0237 | [0.0114, 0.0392] | [1e-05, 0.5] | 1 / hour | yes |
| `K_ind` | `bounded_above_only` | 0.0188 | [0.0103, 0.12] | [0.01, 100] | gram / liter | no |
| `qF` | `identified` | 5.61 | [4.2, 7.94] | [0.01, 1e+03] | filter_paper_unit / gram / hour | yes |
| `kF` | `bounded_above_only` | 5.33e-05 | [1.21e-06, 0.004] | [1e-06, 0.1] | 1 / hour | no |
| `qB` | `identified` | 13.3 | [9.9, 18.7] | [0.01, 3e+03] | beta_glucosidase_assay_unit / gram / hour | yes |
| `kB` | `bounded_above_only` | 4.16e-05 | [1.21e-06, 0.0028] | [1e-06, 0.1] | 1 / hour | no |

The shared noise multiplier has posterior median 2.25 (95 percent interval 1.95
to 2.63): the residuals are about 2.2 times the assumed 10 percent level, so
every interval above is wider than the assumed error model alone would give.
Five of the nine constants are identified (`k_h`, `Y`, `kd`, `qF` and `qB`);
`Kh` is bounded below only (the data cannot separate hydrolysis saturation
above the measured loadings from first-order kinetics, so the half-saturation
constant has a lower limit and no upper one inside the box); `K_ind`, `kF` and
`kB` are bounded above only (induction is effectively saturated and the two
activity-loss rates are effectively zero over 96 hours, so the data give upper
limits only). Six of the nine frozen least-squares point values lie inside
their credible intervals; the frozen values of `K_ind`, `kF` and `kB` sit
exactly on the lower prior bound, just below the lower end of their intervals.
The finite-difference Fisher information at the best sample has practical rank
8 of 9 with condition number 8.7e+06; its least constrained direction is
dominated by `kB` and `kF`. The posterior predictive bands (400 draws, 0
failed) are stored in the artifact for every observable and loading.

The registry records keep their frozen least-squares point values; their
provenance now names this artifact, the credible interval and the verdict, so
that a parameter the data do not identify is visibly a range rather than a
constant. Nothing in the scientific-mode run changes: an exact record is still
used as the one value it carries.

## Sensitivity variant: per-observable multipliers

`results_per_observable_scales/` records the same data, priors and model with
one multiplier per observable (40 walkers x 6000 steps, burn-in 1500). Its
chain did not meet the declared convergence rule (integrated autocorrelation
times of 270 to 380 steps against 4500 post-burn-in steps; effective sample
sizes 470 to 670), so it carries no verdicts and nothing in the registry cites
it. It is kept because of what it shows about the model: when the observables
may be re-weighted independently, the sampler leaves the least-squares region
entirely. It inflates the biomass multiplier to about 5.4 (credible interval
3.2 to 7.5), tightens the substrate multiplier to about 0.5, and moves the
yield to the lower edge of its prior box with the two specific activities
about five times higher than the frozen fit, while cellulose and the two
activities are then fitted more closely. Under the declared unit-scale error
model this region is far worse than the frozen fit (log posterior -781 against
-572), and eight of the nine frozen point values lie outside its 95 percent
intervals. Read it as a misfit diagnosis, not as a calibration: the hydrolysis
candidate cannot fit biomass and cellulose simultaneously at the assumed 10
percent error, and which observable to trust is a question only replicate
measurements with their own error estimates can settle.

## Replicate recovery status

Step 4 asked to recover raw replicates for Gelain and Pakula first. Neither
was possible in the session that added this machinery:

- The Gelain 2020 Mendeley deposit (`10.17632/shd3wcczsr.2`) holds published
  duplicate means without individual runs or standard deviations; replicates
  can only come from the authors.
- Pakula et al. (2016, `10.1186/s13068-016-0547-5`) is recorded as a
  candidate review (`data/experiments/candidate_reviews/pakula_2016_t_reesei_protein_load_review.yml`,
  status `proposed`, no values) because the network policy denied every
  publisher and repository host, so its additional files were not retrieved.

Until replicate-level data exist, every error model in the repository remains
an assumption, every noise-scale multiplier conflates misfit with noise, and
no identifiability verdict is more than conditional.

## Claim boundary

Posterior and identifiability statements are conditional on the declared prior
box, the supplied observation-error model (and any estimated noise-scale
multipliers), the model structure and a finite chain. They do not establish
global identifiability, empirical validation or biological truth. A parameter
the data do not identify must be kept as the reported range.
