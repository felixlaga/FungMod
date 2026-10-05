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

## What it is not

The six Gelain conditions have informed model criticism since v1 and are not
blind validation. The study makes no claim of biological validation, of
transfer to other strains, substrates or conditions, or of promoting any
constant beyond a retrospective fit. `P0` in `M2` stands for unmeasured soluble
carbon carried in by inoculum and medium and is an explicit unknown.
