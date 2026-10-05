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
`6849c8b3355d7c2f0906e8be0a3c18bab1b5c54926289573fd4e6090dc42eb86`) declares
everything before any fit: the data digests, four models with every parameter's
bounds, units and role, the shared assumed error model with one sampled noise
multiplier, the two stages, the decision rules, the outcome vocabulary, the
excluded claims and an amendment rule. `tests/test_gelain_criticism_plan.py`
pins the digest, so a change to the plan is impossible without a dated
amendment inside the file and a new digest in the test and the ledger.

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

## Stage A results (recorded 2026-10-05)

Plan digest `9bb36f8d53d8dad66fd53beda9239ac1b1984c028018ff885ac44d9620921c4e` (the version before amendment 2, which only added the walker rule); five starts and 250 evaluations per start; every
fold trains on two loadings and predicts the third; held-out predictions were
frozen with the plan digest before scoring
(`data/benchmarks/gelain_2020_criticism/results/stage_a/`).

| Model | Scenario | Mean normalized held-out MSE | Change vs M0 | Screen (R1) |
| --- | --- | --- | --- | --- |
| `M0_baseline` | primary | 0.0907 |  | passed (reference) |
| `M0_baseline` | correlated_assumption | 0.0908 |  | passed (reference) |
| `M1_induction_state` | primary | 0.0882 | +2.7% | failed: pooled normalized held-out error improves by less than the required fraction; an observable worsens by more than the allowed fraction |
| `M1_induction_state` | correlated_assumption | 0.0963 | -6.1% | failed: pooled normalized held-out error improves by less than the required fraction; an observable worsens by more than the allowed fraction |
| `M2_soluble_product_pool` | primary | 0.0695 | +23.4% | failed: an observable worsens by more than the allowed fraction |
| `M2_soluble_product_pool` | correlated_assumption | 0.0802 | +11.6% | failed: an observable worsens by more than the allowed fraction |
| `M3_conversion_dependent_accessibility` | primary | 0.0979 | -7.9% | failed: pooled normalized held-out error improves by less than the required fraction; an observable worsens by more than the allowed fraction |
| `M3_conversion_dependent_accessibility` | correlated_assumption | 0.1163 | -28.1% | failed: pooled normalized held-out error improves by less than the required fraction; an observable worsens by more than the allowed fraction |

Per-observable pooled normalized held-out MSE, primary scenario:

| Model | biomass | substrate | cellulase activity | beta-glucosidase activity |
| --- | --- | --- | --- | --- |
| `M0_baseline` | 0.0815 | 0.0137 | 0.1566 | 0.1110 |
| `M1_induction_state` | 0.0792 | 0.0155 | 0.1523 | 0.1060 |
| `M2_soluble_product_pool` | 0.1067 | 0.0078 | 0.1034 | 0.0601 |
| `M3_conversion_dependent_accessibility` | 0.0753 | 0.0143 | 0.1825 | 0.1195 |

Every fit had full practical rank in every fold and in the all-condition fit.
Verdicts in the plan's vocabulary:

- `M1_induction_state`: **not supported**. The induced state improves the
  all-condition fit (cost 1.876 against 2.015 for M0) but held-out error improves by
  only 2.7 percent and substrate worsens by 13 percent; the memory constant
  settles near 0.13 per hour.
- `M2_soluble_product_pool`: **not supported** under R1, and the most
  informative failure. Pooled held-out error improves by 23 percent (primary)
  and 12 percent (correlated), with substrate, cellulase and beta-glucosidase
  all clearly better, but biomass worsens by 31 percent, above the 10 percent
  the plan allows. The all-condition fit removes biomass loss
  (kd 3.8e-05 per hour), lowers the yield to 0.18, pushes the
  initial soluble pool to 2.86 g/L near the top of its declared
  range, makes uptake nearly saturated (Ks 0.0012 g/L) and leaves
  product inhibition weak (Ki 73 g/L). The biomass/cellulose
  tension of BAYES-001 reappears as a trade: the pool fits every other
  observable by giving up biomass.
- `M3_conversion_dependent_accessibility`: **not supported**. Held-out error
  is 8 percent worse than the baseline (28 percent under the correlated
  assumption) and both activities worsen; the exponent settles at
  0.10, which nearly recovers the baseline.

No model passed the screen, so no profiles were run and no holdout posteriors
are planned. Stage B all-condition posteriors (adequacy R2, identifiability
R3, coverage R4) follow for the three additions; M0 reuses BAYES-001.

## Stage B results (recorded 2026-10-05, in progress)

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
  plan's vocabulary: **not supported (fails R1)**, with the provisional R2 and
  R3 verdicts recorded alongside.
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
- `M3_conversion_dependent_accessibility`: running; recorded here when its
  chain completes.
- `M0_baseline`: BAYES-001's frozen chain (converged; five constants
  identified, four bounded on one side; multiplier 2.25).

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
