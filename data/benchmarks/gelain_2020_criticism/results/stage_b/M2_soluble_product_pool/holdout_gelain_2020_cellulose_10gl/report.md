# gelain_2020_model_criticism_v1: stage B, M2_soluble_product_pool

Hydrolysis releases a soluble product pool P that is taken up by Monod growth and inhibits hydrolysis: consumption = k_h F S/(Kh+S) / (1 + P/Ki) -> P; uptake = (mu/Y) X P/(Ks+P) -> Y X + (1-Y) ledger; P(0) = P0 stands for soluble carbon carried in by inoculum and medium and is not measured. Biomass loss and activity production as M0 (induction by cellulose S).

Converged by the declared rule: **False** (mean acceptance 0.214, 6000 post-burn-in steps, 28 walkers). Verdicts below are **provisional (chain not converged by the declared rule)**.

| Parameter | Added | Class | Median | 95% interval | Prior box | Width / prior width | tau | tau reliable |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `k_h` |  | identified | 0.02638 | [0.00967, 0.0572] | [1e-06, 1] | 0.13 | 489 | False |
| `Kh` |  | bounded_below_only | 44.04 | [11.6, 95.8] | [0.001, 100] | 0.18 | 467 | False |
| `Y` |  | identified | 0.6099 | [0.472, 0.824] | [0.01, 1] | 0.12 | 440 | False |
| `kd` |  | identified | 0.03791 | [0.0256, 0.0579] | [1e-05, 0.5] | 0.08 | 414 | False |
| `K_ind` |  | bounded_above_only | 0.02111 | [0.0103, 0.158] | [0.01, 100] | 0.30 | 391 | False |
| `qF` |  | identified | 2.894 | [2.33, 3.68] | [0.01, 1e+03] | 0.04 | 412 | False |
| `kF` |  | bounded_above_only | 4.005e-05 | [1.2e-06, 0.00346] | [1e-06, 0.1] | 0.69 | 469 | False |
| `qB` |  | identified | 7.16 | [5.85, 9.07] | [0.01, 3e+03] | 0.03 | 392 | False |
| `kB` |  | bounded_above_only | 2.784e-05 | [1.18e-06, 0.00185] | [1e-06, 0.1] | 0.64 | 422 | False |
| `mu` | yes | bounded_below_only | 0.7522 | [0.243, 1.88] | [0.001, 2] | 0.27 | 500 | False |
| `Ks` | yes | bounded_above_only | 0.02168 | [0.00119, 0.95] | [0.001, 10] | 0.73 | 407 | False |
| `Ki` | yes | prior_dominated | 2.543 | [0.0148, 83.4] | [0.01, 100] | 0.94 | 440 | False |
| `P0` | yes | bounded_below_only | 2.753 | [1.47, 2.99] | [0.001, 3] | 0.09 | 365 | False |

| Noise-scale multiplier | Posterior median | 95% interval |
| --- | --- | --- |
| `all_observables` | 1.46 | [1.23, 1.78] |

Decision rules (provisional):

- R1 holdout support (stage A screen, primary): None
- R2 adequacy (multiplier interval contains 1.0): False; interval [1.2274922741982663, 1.7839468712773325]
- R3 identification of added parameters: False; classes {'mu': 'bounded_below_only', 'Ks': 'bounded_above_only', 'Ki': 'prior_dominated', 'P0': 'bounded_below_only'}
- Outcome: **not scored (stage A screen not recorded)**

Holdout posterior: the likelihood used `gelain_2020_cellulose_20gl`, `gelain_2020_cellulose_30gl` only; `gelain_2020_cellulose_10gl` is held out and scored below by held-out posterior predictive coverage.

Posterior predictive coverage at 95% with measurement noise (400 draws, 0 failed):

- biomass: 16/16 inside (100%)
- substrate: 16/16 inside (100%)
- cellulase_activity: 16/16 inside (100%)
- beta_glucosidase_activity: 16/16 inside (100%)
- all_observables: 64/64 inside (100%)

Held-out posterior predictive coverage (`gelain_2020_cellulose_10gl`, 400 draws, 0 failed; the likelihood never saw these observations):

- biomass: 8/8 inside (100%)
- substrate: 8/8 inside (100%)
- cellulase_activity: 2/8 inside (25%)
- beta_glucosidase_activity: 4/8 inside (50%)
- all_observables: 22/32 inside (69%)

Claims excluded by the plan: biological validation; blind or independent prediction; transfer to other strains, substrates or conditions; promotion of any constant beyond retrospective fit.
