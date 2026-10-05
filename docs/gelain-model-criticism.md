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
`9bb36f8d53d8dad66fd53beda9239ac1b1984c028018ff885ac44d9620921c4e`) declares
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

## What it is not

The six Gelain conditions have informed model criticism since v1 and are not
blind validation. The study makes no claim of biological validation, of
transfer to other strains, substrates or conditions, or of promoting any
constant beyond a retrospective fit. `P0` in `M2` stands for unmeasured soluble
carbon carried in by inoculum and medium and is an explicit unknown.
