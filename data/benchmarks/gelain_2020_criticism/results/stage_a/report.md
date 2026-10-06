# gelain_2020_model_criticism_v1: stage A

Retrospective model criticism on published duplicate means that have already informed earlier model development (v1, v2 and BAYES-001). Nothing here is blind, independent or a validation of biology.

Plan digest `9897ab11026a81794a27f512264afa5ed70f341f23f1d73264076956497d43d7`; 5 starts, 250 evaluations per start; log-space finite-difference step 0.001, tolerances ftol 1e-10, xtol 1e-10, gtol 1e-10, up to 3 restarts of the best start until the relative cost decrease is below 1e-06.

| Model | Scenario | Folds scored | Mean normalized held-out MSE | Improvement vs M0 | Full rank everywhere | Screen |
| --- | --- | --- | --- | --- | --- | --- |
| M0_baseline | primary | 3/3 | 0.09184 |  | True | passed |
| M0_baseline | correlated_assumption | 3/3 | 0.09324 |  | True | passed |
| M1_induction_state | primary | 3/3 | 0.09173 | +0.1% | True | failed: pooled normalized held-out error improves by less than the required fraction; an observable worsens by more than the allowed fraction |
| M1_induction_state | correlated_assumption | 3/3 | 0.09606 | -3.0% | True | failed: pooled normalized held-out error improves by less than the required fraction; an observable worsens by more than the allowed fraction |
| M2_soluble_product_pool | primary | 3/3 | 0.0703 | +23.4% | True | passed |
| M2_soluble_product_pool | correlated_assumption | 3/3 | 0.0689 | +26.1% | True | passed |
| M3_conversion_dependent_accessibility | primary | 3/3 | 0.09201 | -0.2% | True | failed: pooled normalized held-out error improves by less than the required fraction |
| M3_conversion_dependent_accessibility | correlated_assumption | 3/3 | 0.0979 | -5.0% | True | failed: pooled normalized held-out error improves by less than the required fraction; an observable worsens by more than the allowed fraction |

Per-observable pooled normalized held-out MSE (primary scenario):

| Model | biomass | substrate | cellulase_activity | beta_glucosidase_activity |
| --- | --- | --- | --- | --- |
| M0_baseline | 0.07863 | 0.01323 | 0.1603 | 0.1152 |
| M1_induction_state | 0.06378 | 0.04101 | 0.1542 | 0.1079 |
| M2_soluble_product_pool | 0.0592 | 0.01128 | 0.127 | 0.08372 |
| M3_conversion_dependent_accessibility | 0.07387 | 0.01209 | 0.1648 | 0.1173 |

Claims excluded by the plan: biological validation; blind or independent prediction; transfer to other strains, substrates or conditions; promotion of any constant beyond retrospective fit.
