# gelain_2020_model_criticism_v1: stage B, M2_soluble_product_pool

Hydrolysis releases a soluble product pool P that is taken up by Monod growth and inhibits hydrolysis: consumption = k_h F S/(Kh+S) / (1 + P/Ki) -> P; uptake = (mu/Y) X P/(Ks+P) -> Y X + (1-Y) ledger; P(0) = P0 stands for soluble carbon carried in by inoculum and medium and is not measured. Biomass loss and activity production as M0 (induction by cellulose S).

Converged by the declared rule: **False** (mean acceptance 0.203, 6000 post-burn-in steps, 28 walkers). Verdicts below are **provisional (chain not converged by the declared rule)**.

| Parameter | Added | Class | Median | 95% interval | Prior box | Width / prior width | tau | tau reliable |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `k_h` |  | identified | 0.01298 | [0.00357, 0.0534] | [1e-06, 1] | 0.20 | 364 | False |
| `Kh` |  | bounded_below_only | 21.81 | [3.43, 89.4] | [0.001, 100] | 0.28 | 363 | False |
| `Y` |  | identified | 0.6034 | [0.445, 0.827] | [0.01, 1] | 0.13 | 442 | False |
| `kd` |  | identified | 0.02714 | [0.0167, 0.0435] | [1e-05, 0.5] | 0.09 | 408 | False |
| `K_ind` |  | bounded_above_only | 0.02031 | [0.0103, 0.124] | [0.01, 100] | 0.27 | 403 | False |
| `qF` |  | identified | 4.375 | [3.43, 5.82] | [0.01, 1e+03] | 0.05 | 434 | False |
| `kF` |  | bounded_above_only | 6.444e-05 | [1.25e-06, 0.00324] | [1e-06, 0.1] | 0.68 | 440 | False |
| `qB` |  | identified | 10.3 | [8.16, 13.8] | [0.01, 3e+03] | 0.04 | 460 | False |
| `kB` |  | weakly_identified | 0.0001262 | [1.38e-06, 0.00341] | [1e-06, 0.1] | 0.68 | 444 | False |
| `mu` | yes | bounded_below_only | 0.7396 | [0.212, 1.92] | [0.001, 2] | 0.29 | 491 | False |
| `Ks` | yes | prior_dominated | 0.04163 | [0.00121, 2.62] | [0.001, 10] | 0.83 | 410 | False |
| `Ki` | yes | prior_dominated | 2.719 | [0.0147, 83] | [0.01, 100] | 0.94 | 461 | False |
| `P0` | yes | bounded_below_only | 2.802 | [2.17, 2.99] | [0.001, 3] | 0.04 | 387 | False |

| Noise-scale multiplier | Posterior median | 95% interval |
| --- | --- | --- |
| `all_observables` | 1.51 | [1.26, 1.86] |

Decision rules (provisional):

- R1 holdout support (stage A screen, primary): None
- R2 adequacy (multiplier interval contains 1.0): False; interval [1.2602372854390498, 1.8577603147759414]
- R3 identification of added parameters: False; classes {'mu': 'bounded_below_only', 'Ks': 'prior_dominated', 'Ki': 'prior_dominated', 'P0': 'bounded_below_only'}
- Outcome: **not scored (stage A screen not recorded)**

Holdout posterior: the likelihood used `gelain_2020_cellulose_10gl`, `gelain_2020_cellulose_20gl` only; `gelain_2020_cellulose_30gl` is held out and scored below by held-out posterior predictive coverage.

Posterior predictive coverage at 95% with measurement noise (400 draws, 0 failed):

- biomass: 16/16 inside (100%)
- substrate: 16/16 inside (100%)
- cellulase_activity: 14/16 inside (88%)
- beta_glucosidase_activity: 16/16 inside (100%)
- all_observables: 62/64 inside (97%)

Held-out posterior predictive coverage (`gelain_2020_cellulose_30gl`, 400 draws, 0 failed; the likelihood never saw these observations):

- biomass: 5/8 inside (62%)
- substrate: 8/8 inside (100%)
- cellulase_activity: 3/8 inside (38%)
- beta_glucosidase_activity: 3/8 inside (38%)
- all_observables: 19/32 inside (59%)

Claims excluded by the plan: biological validation; blind or independent prediction; transfer to other strains, substrates or conditions; promotion of any constant beyond retrospective fit.
