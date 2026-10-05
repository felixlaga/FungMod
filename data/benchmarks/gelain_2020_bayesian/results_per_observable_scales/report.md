# gelain_2020_cellulose_bayesian_per_observable_scales_v1

FungMod posterior sampling of the T. harzianum P49P11 cellulose registry case (hydrolysis candidate) on the Gelain 2020 cellulose cultures at 10, 20 and 30 g/L (article doi:10.1016/j.cesx.2020.100085, data doi:10.17632/shd3wcczsr.2; observations data/benchmarks/gelain_2020_v2/observations.json). Priors are the v2 joint-benchmark bounds, log-uniform. The error model is an assumption (independent Gaussian errors with standard deviation 10 percent of each observable's training maximum, biomass/substrate correlation -0.5) scaled by per-observable multipliers sampled jointly with the parameters; the multipliers absorb model misfit and measurement noise together because the deposit holds no replicates or standard deviations.

Converged by the declared rule: **False** (mean acceptance 0.231, 4500 post-burn-in steps, 40 walkers).

| Symbol | Class | Posterior median | Credible interval | Prior box | Units | Width / prior width | tau |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `gelain_hydrolysis_k_h` | identified | 0.00654 | [0.00398, 0.0154] | [1e-06, 1] | gram / filter_paper_unit / hour | 0.10 | 281 |
| `gelain_hydrolysis_Kh` | identified | 17.72 | [7.93, 62.2] | [0.001, 100] | gram / liter | 0.18 | 292 |
| `gelain_hydrolysis_Y` | bounded_above_only | 0.0124 | [0.0101, 0.318] | [0.01, 1] | dimensionless | 0.75 | 335 |
| `gelain_hydrolysis_kd` | bounded_above_only | 0.0001952 | [1.16e-05, 0.00949] | [1e-05, 0.5] | 1 / hour | 0.62 | 269 |
| `gelain_hydrolysis_K_ind` | bounded_above_only | 0.0336 | [0.0107, 0.331] | [0.01, 100] | gram / liter | 0.37 | 292 |
| `gelain_hydrolysis_qF` | identified | 28.46 | [7.12, 34.6] | [0.01, 1e+03] | filter_paper_unit / gram / hour | 0.14 | 383 |
| `gelain_hydrolysis_kF` | bounded_above_only | 6.577e-05 | [1.25e-06, 0.00585] | [1e-06, 0.1] | 1 / hour | 0.73 | 320 |
| `gelain_hydrolysis_qB` | identified | 67.52 | [15.3, 82.7] | [0.01, 3e+03] | beta_glucosidase_assay_unit / gram / hour | 0.13 | 328 |
| `gelain_hydrolysis_kB` | bounded_above_only | 8.108e-05 | [1.24e-06, 0.00543] | [1e-06, 0.1] | 1 / hour | 0.73 | 352 |

| Noise-scale multiplier | Posterior median | Credible interval |
| --- | --- | --- |
| `biomass` (biomass) | 5.43 | [3.22, 7.53] |
| `substrate` (substrate) | 0.514 | [0.391, 0.724] |
| `cellulase_activity` (cellulase_activity) | 1.77 | [1.31, 2.74] |
| `beta_glucosidase_activity` (beta_glucosidase_activity) | 1.33 | [0.998, 2.21] |

Posterior and identifiability statements are conditional on the declared prior box, the supplied observation-error model (and any estimated noise-scale multipliers, which absorb model misfit), the model structure and a finite chain. They do not establish global identifiability, empirical validation or biological truth; a parameter the data do not identify must be kept as the reported range.

- Exploratory sensitivity variant of the primary study: per-observable noise-scale multipliers. Its chain is shorter than the primary one and did not meet the declared convergence rule; its summaries are reported as evidence about model misfit, not as identifiability verdicts, and nothing in the registry cites it.
- Posterior sampling on published duplicate means; no replicate-level data exist in the deposit, so the multipliers conflate measurement error and model misfit.
- Retrospective development analysis of one strain and preparation; not validation, not a prediction for other conditions.
- Chain not converged by the declared rule; summaries and verdicts are provisional.
