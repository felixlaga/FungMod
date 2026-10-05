# gelain_2020_cellulose_bayesian_v1

FungMod posterior sampling of the T. harzianum P49P11 cellulose registry case (hydrolysis candidate) on the Gelain 2020 cellulose cultures at 10, 20 and 30 g/L (article doi:10.1016/j.cesx.2020.100085, data doi:10.17632/shd3wcczsr.2; observations data/benchmarks/gelain_2020_v2/observations.json). Priors are the v2 joint-benchmark bounds, log-uniform. The error model is an assumption (independent Gaussian errors with standard deviation 10 percent of each observable's training maximum, biomass/substrate correlation -0.5) scaled by one multiplier shared by the four observables and sampled jointly with the parameters; the multiplier sets the overall error level from the residuals, keeps the declared relative weighting, and absorbs model misfit and measurement noise together because the deposit holds no replicates or standard deviations.

Converged by the declared rule: **True** (mean acceptance 0.325, 20000 post-burn-in steps, 24 walkers).

| Symbol | Class | Posterior median | Credible interval | Prior box | Units | Width / prior width | tau |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `gelain_hydrolysis_k_h` | identified | 0.01848 | [0.00714, 0.0639] | [1e-06, 1] | gram / filter_paper_unit / hour | 0.16 | 305 |
| `gelain_hydrolysis_Kh` | bounded_below_only | 18.37 | [4.26, 81.9] | [0.001, 100] | gram / liter | 0.26 | 306 |
| `gelain_hydrolysis_Y` | identified | 0.4783 | [0.328, 0.648] | [0.01, 1] | dimensionless | 0.15 | 299 |
| `gelain_hydrolysis_kd` | identified | 0.02365 | [0.0114, 0.0392] | [1e-05, 0.5] | 1 / hour | 0.11 | 274 |
| `gelain_hydrolysis_K_ind` | bounded_above_only | 0.0188 | [0.0103, 0.12] | [0.01, 100] | gram / liter | 0.27 | 289 |
| `gelain_hydrolysis_qF` | identified | 5.606 | [4.2, 7.94] | [0.01, 1e+03] | filter_paper_unit / gram / hour | 0.06 | 324 |
| `gelain_hydrolysis_kF` | bounded_above_only | 5.331e-05 | [1.21e-06, 0.004] | [1e-06, 0.1] | 1 / hour | 0.70 | 278 |
| `gelain_hydrolysis_qB` | identified | 13.29 | [9.9, 18.7] | [0.01, 3e+03] | beta_glucosidase_assay_unit / gram / hour | 0.05 | 339 |
| `gelain_hydrolysis_kB` | bounded_above_only | 4.161e-05 | [1.21e-06, 0.0028] | [1e-06, 0.1] | 1 / hour | 0.67 | 286 |

| Noise-scale multiplier | Posterior median | Credible interval |
| --- | --- | --- |
| `all_observables` (biomass, substrate, cellulase_activity, beta_glucosidase_activity) | 2.25 | [1.95, 2.63] |

Posterior and identifiability statements are conditional on the declared prior box, the supplied observation-error model (and any estimated noise-scale multipliers, which absorb model misfit), the model structure and a finite chain. They do not establish global identifiability, empirical validation or biological truth; a parameter the data do not identify must be kept as the reported range.

- Posterior sampling on published duplicate means; no replicate-level data exist in the deposit, so the shared noise-scale multiplier conflates measurement error and model misfit.
- The registry records keep their frozen least-squares point values; this study reports which of them the data identify and which must be kept as ranges.
- Retrospective development analysis of one strain and preparation; not validation, not a prediction for other conditions.
