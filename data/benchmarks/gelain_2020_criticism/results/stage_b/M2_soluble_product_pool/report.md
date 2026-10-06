# gelain_2020_model_criticism_v1: stage B, M2_soluble_product_pool

Hydrolysis releases a soluble product pool P that is taken up by Monod growth and inhibits hydrolysis: consumption = k_h F S/(Kh+S) / (1 + P/Ki) -> P; uptake = (mu/Y) X P/(Ks+P) -> Y X + (1-Y) ledger; P(0) = P0 stands for soluble carbon carried in by inoculum and medium and is not measured. Biomass loss and activity production as M0 (induction by cellulose S).

Converged by the declared rule: **False** (mean acceptance 0.194, 28000 post-burn-in steps, 28 walkers). Verdicts below are **provisional (chain not converged by the declared rule)**.

| Parameter | Added | Class | Median | 95% interval | Prior box | Width / prior width | tau | tau reliable |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `k_h` |  | identified | 0.01647 | [0.00605, 0.0857] | [1e-06, 1] | 0.19 | 1393 | False |
| `Kh` |  | bounded_below_only | 23.09 | [5.83, 92.1] | [0.001, 100] | 0.24 | 1176 | False |
| `Y` |  | identified | 0.5217 | [0.391, 0.684] | [0.01, 1] | 0.12 | 824 | False |
| `kd` |  | identified | 0.02806 | [0.0178, 0.0421] | [1e-05, 0.5] | 0.08 | 997 | False |
| `K_ind` |  | bounded_above_only | 0.01885 | [0.0103, 0.11] | [0.01, 100] | 0.26 | 1004 | False |
| `qF` |  | identified | 3.792 | [2.93, 5.11] | [0.01, 1e+03] | 0.05 | 1029 | False |
| `kF` |  | bounded_above_only | 5.516e-05 | [1.24e-06, 0.00334] | [1e-06, 0.1] | 0.69 | 1122 | False |
| `qB` |  | identified | 9.039 | [7.07, 12.1] | [0.01, 3e+03] | 0.04 | 941 | False |
| `kB` |  | bounded_above_only | 3.787e-05 | [1.21e-06, 0.00225] | [1e-06, 0.1] | 0.65 | 885 | False |
| `mu` | yes | bounded_below_only | 0.6326 | [0.176, 1.9] | [0.001, 2] | 0.31 | 1173 | False |
| `Ks` | yes | prior_dominated | 0.02471 | [0.00117, 2.28] | [0.001, 10] | 0.82 | 1211 | False |
| `Ki` | yes | prior_dominated | 0.9905 | [0.0125, 79.1] | [0.01, 100] | 0.95 | 1279 | False |
| `P0` | yes | bounded_below_only | 2.835 | [2.18, 2.99] | [0.001, 3] | 0.04 | 1072 | False |

| Noise-scale multiplier | Posterior median | 95% interval |
| --- | --- | --- |
| `all_observables` | 1.89 | [1.63, 2.23] |

Decision rules (provisional):

- R1 holdout support (stage A screen, primary): True
- R2 adequacy (multiplier interval contains 1.0): False; interval [1.6344227088550727, 2.2281845007666607]
- R3 identification of added parameters: False; classes {'mu': 'bounded_below_only', 'Ks': 'prior_dominated', 'Ki': 'prior_dominated', 'P0': 'bounded_below_only'}
- Outcome: **improves fit but unidentified (R1, not R3)**

Posterior predictive coverage at 95% with measurement noise (400 draws, 0 failed):

- biomass: 24/24 inside (100%)
- substrate: 24/24 inside (100%)
- cellulase_activity: 19/24 inside (79%)
- beta_glucosidase_activity: 24/24 inside (100%)
- all_observables: 91/96 inside (95%)

Claims excluded by the plan: biological validation; blind or independent prediction; transfer to other strains, substrates or conditions; promotion of any constant beyond retrospective fit.
