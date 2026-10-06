# Gelain 2020 model-criticism study

A preregistered comparison of explicit mechanisms added to the registry
hydrolysis candidate (`trichoderma_harzianum_p49p11` x `cellulose_celufloc_200`)
on the three Gelain 2020 cellulose loadings. The question is narrow: which
mechanism reduces the biomass/cellulose misfit that the
[Bayesian study](bayesian-calibration.md) found (a shared noise multiplier of
2.25 at the assumed 10 percent error), and which of its added parameters do
the published duplicate means identify. It is retrospective model criticism on
data that already informed earlier development; it is never blind, never
independent and validates no biology.

## The frozen plan

`data/benchmarks/gelain_2020_criticism/plan.json` (SHA-256
`9897ab11026a81794a27f512264afa5ed70f341f23f1d73264076956497d43d7`) declares
everything before any fit: the data digests, four models with every parameter's
bounds, units and role, the shared assumed error model with one sampled noise
multiplier, the two stages, the decision rules, the outcome vocabulary, the
excluded claims and an amendment rule. `tests/test_gelain_criticism_plan.py`
pins the digest, so a change to the plan is impossible without a dated
amendment inside the file and a new digest in the test and the ledger.

Three dated amendments are recorded in the file. The first two (digests
`8b368ac8...` to `9bb36f8d...` to `6849c8b3...`) added machine-readable
error-model fields and the walker rule before the runs they affect. The third
(`6849c8b3...` to the current digest) added the stage A optimiser settings
after the cross-solver reproduction (PETAB-001) showed that FungMod's recorded
`M0_baseline` optimum was 1.3 percent above the minimum COPASI found. The
diagnosis, recorded in the amendment: every start had stopped on scipy's step
tolerance rather than the evaluation cap; the cost gradient at the recorded
point was far from zero; and the finite-difference Jacobian at scipy's default
step (about 1.5e-8) was differentiating the adaptive ODE integrator's step
noise, so derivative norms for weakly entering constants were 15 times their
converged values and the trust region collapsed. The v2 plan had declared a
log-space difference step of 1e-3 and this plan omitted it. The amendment
declares that step, tolerances of 1e-10, and up to three restarts of the best
start until the relative cost decrease is below 1e-6; `OptimiserSettings`
reads the block with no defaults, and every fit file records the settings and
its restarts. Stage A was re-run for every model and scenario under the new
digest; the stage B chains were not re-run (their initial centre is a starting
point, and they are already reported as unconverged and provisional), and
their R1 component is checked against the new screen by
`tests/test_gelain_criticism_plan.py`.

| Model | Mechanism added to the baseline | Added parameters |
| --- | --- | --- |
| `M0_baseline` | none (the registry case) | none |
| `M1_induction_state` | enzyme synthesis follows an induced-biomass state `z` with a memory time constant | `kz_loss` (`k_z` fixed at 1 per hour) |
| `M2_soluble_product_pool` | hydrolysis releases a soluble pool that Monod growth takes up and that inhibits hydrolysis; the initial pool is an explicit unknown | `mu`, `Ks`, `Ki`, `P0` |
| `M3_conversion_dependent_accessibility` | hydrolysis is multiplied by `(S / S0)^n` (Kadam, Rydholm and McMillan 2004, generalised by an exponent) | `n` |

Every variant is composed in `fungal_model.research.gelain_criticism` from the
registry base configuration and generic process laws: proportional synthesis,
first-order loss, enzyme-explicit Michaelis-Menten with product maps, the
product-inhibition modifier, and the new generic
`substrate_reactivity` rate modifier (`fungal_model.modifiers.reactivity`).
The registry records are not changed; the variants run in exploratory mode
because their added constants are study candidates, and each candidate value
carries the study as its source.

## Stages

- **Stage A** (`run_stage_a`): for every model and scenario, an all-condition
  least-squares fit and three whole-condition holdouts (train on two loadings,
  predict the third), each held-out prediction frozen with the plan digest
  before scoring. The v2 complexity screen then judges each model against the
  baseline, and profiles run for models that pass.
- **Stage B** (`build_posterior_study`, `sample_posterior_study`): the ensemble
  sampler over the model's log-uniform priors and the shared noise multiplier,
  centred on the stage A fit, with the BAYES-001 identifiability thresholds,
  posterior predictive bands, and the new
  `posterior_predictive_coverage` statistic (the fraction of observations
  inside the 95 percent predictive interval with measurement noise).

```bash
python scripts/run_gelain_2020_model_criticism.py stage-a
python scripts/run_gelain_2020_model_criticism.py stage-b --model M1_induction_state --processes 4
```

Outputs go to `data/benchmarks/gelain_2020_criticism/results/` and cite the
plan digest. A model is reported with one of four words only: supported,
improves fit but unidentified, not supported, or not run with its reason.

## Stage A results (re-recorded 2026-10-05 under amendment 3)

Plan digest `9897ab11026a81794a27f512264afa5ed70f341f23f1d73264076956497d43d7`;
five starts and 250 evaluations per start with the declared optimiser
(log-space finite-difference step 1e-3, tolerances 1e-10, up to three
restarts of the best start); every fold trains on two loadings and predicts
the third; held-out predictions were frozen with the plan digest before
scoring (`data/benchmarks/gelain_2020_criticism/results/stage_a/`). The first
stage A run (digest `9bb36f8d...`, scipy's default difference step) is
superseded; its verdicts and the reason are given at the end of this section.

| Model | Scenario | Mean normalized held-out MSE | Change vs M0 | Screen (R1) |
| --- | --- | --- | --- | --- |
| `M0_baseline` | primary | 0.0918 |  | passed (reference) |
| `M0_baseline` | correlated_assumption | 0.0932 |  | passed (reference) |
| `M1_induction_state` | primary | 0.0917 | +0.1% | failed: pooled normalized held-out error improves by less than the required fraction; an observable worsens by more than the allowed fraction |
| `M1_induction_state` | correlated_assumption | 0.0961 | -3.0% | failed: pooled normalized held-out error improves by less than the required fraction; an observable worsens by more than the allowed fraction |
| `M2_soluble_product_pool` | primary | 0.0703 | +23.4% | passed |
| `M2_soluble_product_pool` | correlated_assumption | 0.0689 | +26.1% | passed |
| `M3_conversion_dependent_accessibility` | primary | 0.0920 | -0.2% | failed: pooled normalized held-out error improves by less than the required fraction |
| `M3_conversion_dependent_accessibility` | correlated_assumption | 0.0979 | -5.0% | failed: pooled normalized held-out error improves by less than the required fraction; an observable worsens by more than the allowed fraction |

Per-observable pooled normalized held-out MSE, primary scenario:

| Model | biomass | substrate | cellulase activity | beta-glucosidase activity |
| --- | --- | --- | --- | --- |
| `M0_baseline` | 0.0786 | 0.0132 | 0.1603 | 0.1152 |
| `M1_induction_state` | 0.0638 | 0.0410 | 0.1542 | 0.1079 |
| `M2_soluble_product_pool` | 0.0592 | 0.0113 | 0.1270 | 0.0837 |
| `M3_conversion_dependent_accessibility` | 0.0739 | 0.0121 | 0.1648 | 0.1173 |

Every fit had full practical rank in every fold and in the all-condition fit,
and every start of every all-condition fit converged to the same cost (M0
1.988, M1 1.864, M3 1.954; M2 1.414 from three of five starts, the other two
in local minima at 1.45 and 1.81). The baseline's all-condition fit puts
`K_ind`, `kF` and `kB` on their lower bounds (projected gradient norm 2.5e-3
in log space); it is the fit the cross-solver study reproduces. Verdicts in
the plan's vocabulary:

- `M1_induction_state`: **not supported**. The induced state lowers the
  all-condition cost (1.864 against 1.988) and improves held-out biomass by
  19 percent, but the pooled held-out error is unchanged (0.1 percent better)
  and substrate is three times worse (0.041 against 0.013); the memory
  constant settles at 0.094 per hour with the specific production rates five
  to six times lower than the baseline's, so the induced state absorbs the
  synthesis dynamics and the cellulose course pays for it.
- `M2_soluble_product_pool`: **passes R1** in both scenarios. Pooled held-out
  error is 23 percent lower (primary) and 26 percent lower (correlated), and
  every observable improves: biomass by 25 and 36 percent, substrate by 15
  and 21, cellulase by 21 and 21, beta-glucosidase by 27 and 26. The
  all-condition fit (cost 1.414 against 1.988) keeps the yield at 0.46 and
  the biomass loss at 0.025 per hour, makes uptake nearly saturated
  (`Ks` 0.0016 g/L, `mu` 0.23 per hour), leaves product inhibition weak
  (`Ki` 47 g/L) and puts the initial soluble pool `P0` on the top of its
  declared range (3 g/L); the held-out folds also touch the `Ks`, `Ki` and
  `P0` bounds. The screen is the holdout rule only: what the data say about
  these constants is stage B's question, and the answer recorded there is
  that they are not identified.
- `M3_conversion_dependent_accessibility`: **not supported**. Pooled held-out
  error is 0.2 percent worse than the baseline (5 percent under the
  correlated assumption, where substrate worsens by 12 percent); the exponent
  settles at 0.16, which nearly recovers the baseline.

Profiles (nuisance-reoptimised loss at fitted value times 0.5, 1 and 2,
`results/stage_a/M2_soluble_product_pool/profiles_primary.json`) ran for M2
as the plan requires for a model that passes the screen. Against the
reference cost of 1.4135, halving or doubling `Y`, `qF`, `qB` or `kd`, or
halving `mu` or `P0`, raises the re-optimised cost to between 1.50 and 1.85;
`k_h` and `Kh` raise it to 1.43 to 1.45; `Ks`, `Ki`, `kF`, `kB` and `K_ind`
leave it within 1e-3 of the reference at both factors, which is the
least-squares counterpart of the prior-dominated and one-sided classes that
stage B assigns to the pool's constants. Several nuisance refits reached
1.4132, 2e-4 below the reference, so the all-condition fit sits in a valley
where the declared restart tolerance (1e-6) stops earlier than the
warm-started profile refits do; the plan's `reference_improved` flag records
it for those parameters.

What the first run had said, and why it changed. Under the first stage A
run (five starts, scipy's default finite-difference step of about 1.5e-8)
M0's held-out error was 0.0907, M1's 0.0882 (+2.7 percent), M2's 0.0695
(+23.4 percent, but biomass 31 percent worse) and M3's 0.0979 (-7.9 percent);
no model passed R1, and the recorded verdict for M2 was "not supported" on
the biomass clause alone. The cross-solver study then found the baseline's
optimum 1.3 percent above the minimum COPASI reached, the diagnosis traced it
to the difference step (see the amendment text above), and the whole stage
was re-run. The pooled numbers barely moved (M2's pooled improvement is the
same 23 percent); the per-observable pattern did, because the stalled M2 fit
had traded biomass for the other three observables and the converged one
does not. The first run's files are not kept; its numbers survive in the
ledger (CRIT-001) and in the amendment log.

## Stage B results (recorded 2026-10-05)

Each addition gets one all-condition posterior under the plan's sampler
settings (24 walkers or twice the dimension, 8000 steps, 2000 burn-in, the
shared noise multiplier sampled jointly), centred on its stage A fit. A chain
that misses the declared convergence rule (every autocorrelation time
reliable, every effective sample size at least 100) is reported as not
converged and its verdicts are labelled provisional, as the plan requires.
Outputs live in `results/stage_b/<model>/` (`bayesian_calibration.json`,
`posterior_samples.csv`, `coverage.json`, `verdicts.json`, `report.md`,
`inputs.json`, `artifacts.json`).

- `M2_soluble_product_pool` (28 walkers, 14 coordinates): **not converged**,
  verdicts **provisional**. Integrated autocorrelation times 368 to 529 steps
  against 6000 post-burn-in steps (the rule needs more than 50 tau), effective
  sample sizes 318 to 457, mean acceptance 0.174 (minimum 0.071), two hours
  and thirty-five minutes of wall-clock across two resumed runs against the
  plan's two-hour cap. R2 fails: the shared noise multiplier's 95 percent
  interval is [1.65, 2.87] (median 1.94), which does not contain 1.0, so the
  soluble pool does not make the candidate adequate at the assumed 10 percent
  error (M0: 2.25, [1.95, 2.63]). R3 fails: the added uptake rate `mu`,
  half-saturation `Ks` and inhibition constant `Ki` are prior dominated
  (credible intervals 79 to 94 percent of their prior width) and the initial
  pool `P0` is bounded below only (median 2.8 g/L against an upper bound of
  3 g/L). Of the nine common constants, `qF` and `qB` stay identified,
  `k_h` and `kd` fall to weakly identified, and `Y` and `kF` become prior
  dominated; the pool absorbs what BAYES-001 identified. Posterior predictive
  coverage with measurement noise is 95 of 96 observations (biomass,
  substrate and beta-glucosidase 24 of 24, cellulase 23 of 24). Outcome in the
  plan's vocabulary: **improves fit but unidentified (R1, not R3)**, with the
  provisional R2 and R3 verdicts recorded alongside. The chain was centred on
  the first stage A fit (yield 0.18, biomass loss near zero) and is not
  re-run under amendment 3; its R1 component was refreshed against the new
  screen (`refresh-verdicts`), and a chain centred on the converged fit is
  the next recorded task. Under the first run's screen the outcome had been
  "not supported (fails R1)".
- `M1_induction_state` (24 walkers, 11 coordinates): **not converged**,
  verdicts **provisional**. Autocorrelation times 267 to 340 steps against
  6000 post-burn-in steps, effective sample sizes 423 to 540, mean acceptance
  0.264, 49 minutes of wall-clock. R2 fails: the multiplier's interval is
  [1.87, 2.53] (median 2.16), indistinguishable from the baseline's 2.25, so
  the induced state does not change the misfit level. R3 passes: the added
  memory constant `kz_loss` is weakly identified (median 0.053 per hour,
  interval [0.024, 0.58], 35 percent of the prior width). Of the common
  constants `Y`, `kd`, `qF` and `qB` stay identified (`qF` and `qB` now
  scale the induced pool, medians 0.60 and 1.41), `k_h`, `Kh` and `kz_loss`
  are weakly identified, `K_ind` is bounded above only and `kF`, `kB` prior
  dominated. Coverage 91 of 96 (cellulase 19 of 24). Outcome: **not
  supported (fails R1)**; its R3 pass is the one added parameter the data
  constrain among the three mechanisms.
- `M3_conversion_dependent_accessibility` (24 walkers, 11 coordinates):
  **not converged**, verdicts **provisional**. Autocorrelation times 232 to
  371 steps against 6000 post-burn-in steps, effective sample sizes 388 to
  620, mean acceptance 0.290, 42 minutes of wall-clock. R2 fails: the
  multiplier's interval is [1.94, 2.62] (median 2.24), the baseline's value.
  R3 fails: the accessibility exponent `n` is bounded above only (median
  0.13, interval [0.053, 0.46] against a prior of [0.05, 3]); the data push
  it towards the lower bound where the baseline is recovered. The common
  constants keep the baseline's classes (`k_h`, `Y`, `kd`, `qF`, `qB`
  identified; `Kh` weakly identified; `K_ind`, `kF`, `kB` bounded above
  only). Coverage 91 of 96. Outcome: **not supported (fails R1)**.
- `M0_baseline`: BAYES-001's frozen chain (converged; five constants
  identified, four bounded on one side; multiplier 2.25).

Summary across the three additions: M2 passes R1 under the amended stage A
and M1 and M3 do not; none restores adequacy under R2 (every multiplier
interval excludes 1.0 and overlaps the baseline's 2.25); only M1's memory
constant is weakly identified under R3, while M2's four added constants and
M3's exponent are not. M2 is therefore the one mechanism the holdouts
support and the one whose constants the duplicate means do not identify,
on a chain that started from the superseded fit. None of the three
chains meets the convergence rule at the planned 8000 steps (the largest
autocorrelation times are 340 to 529 steps against 6000 post-burn-in
steps), so every stage B verdict is provisional as the plan requires;
longer chains would need a dated amendment and more than the plan's
two-hour compute cap per chain.
A posterior-study bug surfaced on M1: the sampler supplies only the fitted
symbols, and the variant factory dropped M1's fixed constant `k_z`, so every
starting walker had a non-finite posterior. The factory now merges the
variant's fixed constants into every candidate; a regression test covers it.

## What it is not

The six Gelain conditions have informed model criticism since v1 and are not
blind validation. The study makes no claim of biological validation, of
transfer to other strains, substrates or conditions, or of promoting any
constant beyond a retrospective fit. `P0` in `M2` stands for unmeasured soluble
carbon carried in by inoculum and medium and is an explicit unknown.
