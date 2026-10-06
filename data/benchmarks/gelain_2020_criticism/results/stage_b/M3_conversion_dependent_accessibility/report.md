# gelain_2020_model_criticism_v1: stage B, M3_conversion_dependent_accessibility

Hydrolysis slows with conversion independent of enzyme activity: consumption = k_h F S/(Kh+S) (S/S0)^n, the substrate reactivity factor of Kadam, Rydholm and McMillan (2004, Biotechnol. Prog. 20:698-705, doi:10.1021/bp034316x) generalised by an exponent. Everything else as M0.

Converged by the declared rule: **False** (mean acceptance 0.290, 6000 post-burn-in steps, 24 walkers). Verdicts below are **provisional (chain not converged by the declared rule)**.

| Parameter | Added | Class | Median | 95% interval | Prior box | Width / prior width | tau | tau reliable |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `k_h` |  | identified | 0.01885 | [0.00818, 0.0805] | [1e-06, 1] | 0.17 | 258 | False |
| `Kh` |  | weakly_identified | 10.63 | [1.72, 66] | [0.001, 100] | 0.32 | 295 | False |
| `Y` |  | identified | 0.4955 | [0.352, 0.665] | [0.01, 1] | 0.14 | 246 | False |
| `kd` |  | identified | 0.02426 | [0.0129, 0.0397] | [1e-05, 0.5] | 0.10 | 233 | False |
| `K_ind` |  | bounded_above_only | 0.01868 | [0.0103, 0.14] | [0.01, 100] | 0.28 | 273 | False |
| `qF` |  | identified | 4.894 | [3.41, 6.99] | [0.01, 1e+03] | 0.06 | 269 | False |
| `kF` |  | bounded_above_only | 5.153e-05 | [1.2e-06, 0.00388] | [1e-06, 0.1] | 0.70 | 236 | False |
| `qB` |  | identified | 11.75 | [8.19, 16.8] | [0.01, 3e+03] | 0.06 | 259 | False |
| `kB` |  | bounded_above_only | 3.941e-05 | [1.17e-06, 0.00315] | [1e-06, 0.1] | 0.69 | 311 | False |
| `n` | yes | bounded_above_only | 0.1322 | [0.0529, 0.46] | [0.05, 3] | 0.53 | 371 | False |

| Noise-scale multiplier | Posterior median | 95% interval |
| --- | --- | --- |
| `all_observables` | 2.24 | [1.94, 2.62] |

Decision rules (provisional):

- R1 holdout support (stage A screen, primary): False
- R2 adequacy (multiplier interval contains 1.0): False; interval [1.9361113878231215, 2.6221487800686822]
- R3 identification of added parameters: False; classes {'n': 'bounded_above_only'}
- Outcome: **not supported (fails R1)**

Posterior predictive coverage at 95% with measurement noise (400 draws, 0 failed):

- biomass: 24/24 inside (100%)
- substrate: 24/24 inside (100%)
- cellulase_activity: 19/24 inside (79%)
- beta_glucosidase_activity: 24/24 inside (100%)
- all_observables: 91/96 inside (95%)

Claims excluded by the plan: biological validation; blind or independent prediction; transfer to other strains, substrates or conditions; promotion of any constant beyond retrospective fit.
