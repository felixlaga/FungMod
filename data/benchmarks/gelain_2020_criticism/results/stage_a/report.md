# gelain_2020_model_criticism_v1: stage A

Retrospective model criticism on published duplicate means that have already informed earlier model development (v1, v2 and BAYES-001). Nothing here is blind, independent or a validation of biology.

Plan digest `9bb36f8d53d8dad66fd53beda9239ac1b1984c028018ff885ac44d9620921c4e`; 5 starts, 250 evaluations per start.

| Model | Scenario | Folds scored | Mean normalized held-out MSE | Improvement vs M0 | Full rank everywhere | Screen |
| --- | --- | --- | --- | --- | --- | --- |
| M0_baseline | primary | 3/3 | 0.09071 |  | True | passed |
| M0_baseline | correlated_assumption | 3/3 | 0.0908 |  | True | passed |
| M1_induction_state | primary | 3/3 | 0.08823 | +2.7% | True | failed: pooled normalized held-out error improves by less than the required fraction; an observable worsens by more than the allowed fraction |
| M1_induction_state | correlated_assumption | 3/3 | 0.09632 | -6.1% | True | failed: pooled normalized held-out error improves by less than the required fraction; an observable worsens by more than the allowed fraction |
| M2_soluble_product_pool | primary | 3/3 | 0.06949 | +23.4% | True | failed: an observable worsens by more than the allowed fraction |
| M2_soluble_product_pool | correlated_assumption | 3/3 | 0.08023 | +11.6% | True | failed: an observable worsens by more than the allowed fraction |
| M3_conversion_dependent_accessibility | primary | 3/3 | 0.09787 | -7.9% | True | failed: pooled normalized held-out error improves by less than the required fraction; an observable worsens by more than the allowed fraction |
| M3_conversion_dependent_accessibility | correlated_assumption | 3/3 | 0.1163 | -28.1% | True | failed: pooled normalized held-out error improves by less than the required fraction; an observable worsens by more than the allowed fraction |

Per-observable pooled normalized held-out MSE (primary scenario):

| Model | biomass | substrate | cellulase_activity | beta_glucosidase_activity |
| --- | --- | --- | --- | --- |
| M0_baseline | 0.08153 | 0.01373 | 0.1566 | 0.111 |
| M1_induction_state | 0.07918 | 0.01548 | 0.1523 | 0.106 |
| M2_soluble_product_pool | 0.1067 | 0.007775 | 0.1034 | 0.06013 |
| M3_conversion_dependent_accessibility | 0.07532 | 0.01425 | 0.1825 | 0.1195 |

Claims excluded by the plan: biological validation; blind or independent prediction; transfer to other strains, substrates or conditions; promotion of any constant beyond retrospective fit.
