# gelain_2020_model_criticism_v1: stage B, M2_soluble_product_pool

Hydrolysis releases a soluble product pool P that is taken up by Monod growth and inhibits hydrolysis: consumption = k_h F S/(Kh+S) / (1 + P/Ki) -> P; uptake = (mu/Y) X P/(Ks+P) -> Y X + (1-Y) ledger; P(0) = P0 stands for soluble carbon carried in by inoculum and medium and is not measured. Biomass loss and activity production as M0 (induction by cellulose S).

Converged by the declared rule: **False** (mean acceptance 0.174, 6000 post-burn-in steps, 28 walkers). Verdicts below are **provisional (chain not converged by the declared rule)**.

| Parameter | Added | Class | Median | 95% interval | Prior box | Width / prior width | tau | tau reliable |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `k_h` |  | weakly_identified | 0.01505 | [0.00137, 0.0507] | [1e-06, 1] | 0.26 | 482 | False |
| `Kh` |  | bounded_below_only | 20.61 | [6.16, 82.2] | [0.001, 100] | 0.23 | 467 | False |
| `Y` |  | prior_dominated | 0.513 | [0.0122, 0.691] | [0.01, 1] | 0.88 | 383 | False |
| `kd` |  | weakly_identified | 0.02712 | [2.06e-05, 0.0424] | [1e-05, 0.5] | 0.71 | 375 | False |
| `K_ind` |  | bounded_above_only | 0.02119 | [0.0103, 0.146] | [0.01, 100] | 0.29 | 456 | False |
| `qF` |  | identified | 3.998 | [3.01, 47.4] | [0.01, 1e+03] | 0.24 | 445 | False |
| `kF` |  | prior_dominated | 4.562e-05 | [1.25e-06, 0.0143] | [1e-06, 0.1] | 0.81 | 379 | False |
| `qB` |  | identified | 9.418 | [7.11, 62] | [0.01, 3e+03] | 0.17 | 460 | False |
| `kB` |  | bounded_above_only | 3.509e-05 | [1.24e-06, 0.00244] | [1e-06, 0.1] | 0.66 | 529 | False |
| `mu` | yes | prior_dominated | 0.3721 | [0.00192, 1.78] | [0.001, 2] | 0.90 | 495 | False |
| `Ks` | yes | prior_dominated | 0.02303 | [0.00122, 1.78] | [0.001, 10] | 0.79 | 448 | False |
| `Ki` | yes | prior_dominated | 1.244 | [0.015, 86.4] | [0.01, 100] | 0.94 | 384 | False |
| `P0` | yes | bounded_below_only | 2.798 | [0.458, 2.99] | [0.001, 3] | 0.23 | 368 | False |

| Noise-scale multiplier | Posterior median | 95% interval |
| --- | --- | --- |
| `all_observables` | 1.94 | [1.65, 2.87] |

Decision rules (provisional):

- R1 holdout support (stage A screen, primary): True
- R2 adequacy (multiplier interval contains 1.0): False; interval [1.6508059240578155, 2.866098022775914]
- R3 identification of added parameters: False; classes {'mu': 'prior_dominated', 'Ks': 'prior_dominated', 'Ki': 'prior_dominated', 'P0': 'bounded_below_only'}
- Outcome: **improves fit but unidentified (R1, not R3)**

Posterior predictive coverage at 95% with measurement noise (400 draws, 0 failed):

- biomass: 24/24 inside (100%)
- substrate: 24/24 inside (100%)
- cellulase_activity: 23/24 inside (96%)
- beta_glucosidase_activity: 24/24 inside (100%)
- all_observables: 95/96 inside (99%)

Claims excluded by the plan: biological validation; blind or independent prediction; transfer to other strains, substrates or conditions; promotion of any constant beyond retrospective fit.
