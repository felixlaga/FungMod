# gelain_2020_model_criticism_v1: stage B, M1_induction_state

Enzyme synthesis follows an induced-biomass state z instead of instantaneous biomass: dz/dt = X S/(K_ind+S) - kz_loss z; dF/dt = qF z - kF F; dB/dt = qB z - kB B. Everything else as M0.

Converged by the declared rule: **False** (mean acceptance 0.264, 6000 post-burn-in steps, 24 walkers). Verdicts below are **provisional (chain not converged by the declared rule)**.

| Parameter | Added | Class | Median | 95% interval | Prior box | Width / prior width | tau | tau reliable |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `k_h` |  | weakly_identified | 0.125 | [0.0155, 0.603] | [1e-06, 1] | 0.27 | 275 | False |
| `Kh` |  | weakly_identified | 11.06 | [1.99, 78.8] | [0.001, 100] | 0.32 | 267 | False |
| `Y` |  | identified | 0.5268 | [0.392, 0.684] | [0.01, 1] | 0.12 | 299 | False |
| `kd` |  | identified | 0.02369 | [0.0145, 0.0357] | [1e-05, 0.5] | 0.08 | 297 | False |
| `K_ind` |  | bounded_above_only | 0.01737 | [0.0103, 0.0825] | [0.01, 100] | 0.23 | 281 | False |
| `qF` |  | identified | 0.6044 | [0.363, 3.81] | [0.01, 1e+03] | 0.20 | 307 | False |
| `kF` |  | prior_dominated | 0.0002621 | [1.39e-06, 0.0112] | [1e-06, 0.1] | 0.78 | 340 | False |
| `qB` |  | identified | 1.41 | [0.834, 8.44] | [0.01, 3e+03] | 0.18 | 310 | False |
| `kB` |  | prior_dominated | 9.347e-05 | [1.23e-06, 0.00795] | [1e-06, 0.1] | 0.76 | 319 | False |
| `kz_loss` | yes | weakly_identified | 0.05279 | [0.0236, 0.582] | [0.0001, 1] | 0.35 | 307 | False |

| Noise-scale multiplier | Posterior median | 95% interval |
| --- | --- | --- |
| `all_observables` | 2.16 | [1.87, 2.53] |

Decision rules (provisional):

- R1 holdout support (stage A screen, primary): False
- R2 adequacy (multiplier interval contains 1.0): False; interval [1.868628277019685, 2.5274378973567786]
- R3 identification of added parameters: True; classes {'kz_loss': 'weakly_identified'}
- Outcome: **not supported (fails R1)**

Posterior predictive coverage at 95% with measurement noise (400 draws, 0 failed):

- biomass: 24/24 inside (100%)
- substrate: 24/24 inside (100%)
- cellulase_activity: 19/24 inside (79%)
- beta_glucosidase_activity: 24/24 inside (100%)
- all_observables: 91/96 inside (95%)

Claims excluded by the plan: biological validation; blind or independent prediction; transfer to other strains, substrates or conditions; promotion of any constant beyond retrospective fit.
