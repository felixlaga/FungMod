# Gelain joint culture benchmark v2

Retrospective development comparison after inspection of v1 residuals. Never blind or independent validation.

| Family | Model | Scenario | Mean normalized held-out MSE | Complexity screen |
|---|---|---|---:|---|
| glycerol | effective | primary | 0.0328653 | True |
| glycerol | published | primary | 0.00594028 | True |
| glycerol | retained | primary | 0.0292451 | True |
| cellulose | effective | primary | 0.109497 | True |
| cellulose | published | primary | 0.0061853 | False |
| cellulose | hydrolysis | primary | 0.0918295 | False |
| cellulose | hydrolysis_retained | primary | 0.0931582 | False |
| cellulose | effective | correlated_assumption | 0.113884 | True |
| cellulose | published | correlated_assumption | 0.00754073 | False |
| cellulose | hydrolysis | correlated_assumption | 0.0949697 | True |
| cellulose | hydrolysis_retained | correlated_assumption | 0.097634 | True |

33/33 folds passed numerical checks; 6/132 starts failed.

No model is promoted to validated. See validation_readiness/ for exact identities and missing evidence.

Full diagnostics, failures, profiles, conditional bootstrap and source activity discrepancies are retained in adjacent JSON files.
