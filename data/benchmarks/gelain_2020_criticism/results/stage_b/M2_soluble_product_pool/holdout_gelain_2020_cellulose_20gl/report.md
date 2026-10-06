# gelain_2020_model_criticism_v1: stage B, M2_soluble_product_pool

Hydrolysis releases a soluble product pool P that is taken up by Monod growth and inhibits hydrolysis: consumption = k_h F S/(Kh+S) / (1 + P/Ki) -> P; uptake = (mu/Y) X P/(Ks+P) -> Y X + (1-Y) ledger; P(0) = P0 stands for soluble carbon carried in by inoculum and medium and is not measured. Biomass loss and activity production as M0 (induction by cellulose S).

Converged by the declared rule: **False** (mean acceptance 0.182, 6000 post-burn-in steps, 28 walkers). Verdicts below are **provisional (chain not converged by the declared rule)**.

| Parameter | Added | Class | Median | 95% interval | Prior box | Width / prior width | tau | tau reliable |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `k_h` |  | identified | 0.01385 | [0.00479, 0.0778] | [1e-06, 1] | 0.20 | 439 | False |
| `Kh` |  | bounded_below_only | 18.03 | [3.96, 91.1] | [0.001, 100] | 0.27 | 426 | False |
| `Y` |  | weakly_identified | 0.463 | [0.17, 0.789] | [0.01, 1] | 0.33 | 433 | False |
| `kd` |  | prior_dominated | 0.02425 | [1.46e-05, 0.0548] | [1e-05, 0.5] | 0.76 | 433 | False |
| `K_ind` |  | bounded_above_only | 0.02438 | [0.0105, 0.312] | [0.01, 100] | 0.37 | 538 | False |
| `qF` |  | identified | 4.404 | [3.05, 9.48] | [0.01, 1e+03] | 0.10 | 482 | False |
| `kF` |  | bounded_above_only | 4.035e-05 | [1.13e-06, 0.00405] | [1e-06, 0.1] | 0.71 | 496 | False |
| `qB` |  | identified | 9.962 | [6.71, 21.6] | [0.01, 3e+03] | 0.09 | 408 | False |
| `kB` |  | bounded_above_only | 9.978e-06 | [1.11e-06, 0.00277] | [1e-06, 0.1] | 0.68 | 565 | False |
| `mu` | yes | bounded_below_only | 0.4737 | [0.124, 1.81] | [0.001, 2] | 0.35 | 499 | False |
| `Ks` | yes | prior_dominated | 0.02259 | [0.00118, 2.64] | [0.001, 10] | 0.84 | 461 | False |
| `Ki` | yes | prior_dominated | 3.447 | [0.0168, 88.3] | [0.01, 100] | 0.93 | 495 | False |
| `P0` | yes | bounded_below_only | 2.655 | [0.308, 2.99] | [0.001, 3] | 0.28 | 347 | False |

| Noise-scale multiplier | Posterior median | 95% interval |
| --- | --- | --- |
| `all_observables` | 2.26 | [1.87, 2.9] |

Decision rules (provisional):

- R1 holdout support (stage A screen, primary): None
- R2 adequacy (multiplier interval contains 1.0): False; interval [1.8703725894416274, 2.8957891255513233]
- R3 identification of added parameters: False; classes {'mu': 'bounded_below_only', 'Ks': 'prior_dominated', 'Ki': 'prior_dominated', 'P0': 'bounded_below_only'}
- Outcome: **not scored (stage A screen not recorded)**

Holdout posterior: the likelihood used `gelain_2020_cellulose_10gl`, `gelain_2020_cellulose_30gl` only; `gelain_2020_cellulose_20gl` is held out and scored below by held-out posterior predictive coverage.

Posterior predictive coverage at 95% with measurement noise (400 draws, 0 failed):

- biomass: 16/16 inside (100%)
- substrate: 16/16 inside (100%)
- cellulase_activity: 15/16 inside (94%)
- beta_glucosidase_activity: 16/16 inside (100%)
- all_observables: 63/64 inside (98%)

Held-out posterior predictive coverage (`gelain_2020_cellulose_20gl`, 400 draws, 0 failed; the likelihood never saw these observations):

- biomass: 8/8 inside (100%)
- substrate: 8/8 inside (100%)
- cellulase_activity: 8/8 inside (100%)
- beta_glucosidase_activity: 8/8 inside (100%)
- all_observables: 32/32 inside (100%)

Claims excluded by the plan: biological validation; blind or independent prediction; transfer to other strains, substrates or conditions; promotion of any constant beyond retrospective fit.
