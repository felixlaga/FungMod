# Gelain culture benchmark

Exploratory retrospective condition holdouts; no empirical uncertainty or independent validation.

RMSE in g/L. Published source scores use all-condition fitted parameters and are descriptive only.

| Held-out condition | Biomass | Substrate | Constant-state biomass | Constant-state substrate |
| --- | ---: | ---: | ---: | ---: |
| gelain_2020_glycerol_5gl | 1.0555 | 0.8983 | 1.6878 | 4.3361 |
| gelain_2020_glycerol_10gl | 0.8726 | 1.3482 | 2.4432 | 8.6624 |
| gelain_2020_glycerol_20gl | 2.2948 | 1.4924 | 3.5234 | 16.7839 |
| gelain_2020_cellulose_10gl | 1.8848 | 1.0864 | 3.5135 | 7.9432 |
| gelain_2020_cellulose_20gl | 1.6140 | 2.8314 | 4.8383 | 15.2839 |
| gelain_2020_cellulose_30gl | 2.4796 | 7.4446 | 5.5635 | 22.2875 |

See report.json for every optimizer start, bound contact, Jacobian diagnostic, weighting sensitivity,
solver/tolerance check, training score and source reproduction result.
No post-holdout model selection is performed. Means are retained as reported, including reversals and zeros.
