# BIO-READINESS-LITE

## Goal

Add a lightweight gate for reusable biological process mechanisms.

## Rule

```text
BIO-* = reusable process mechanism
CASE-* = specific organism/substrate/environment experiment
DATA-* = source/evidence/validation dataset
```

## Required proposal fields

```text
mechanism_id
general_process_family
mathematical_law
state_variables
parameters
units
valid_substrate_classes
valid_enzyme_or_source_classes
environment_variables
output_curves
summary_metrics
assumptions
not_in_scope
unknowns
suggested_experiments
blocking_failure_modes
tests_required
limitations
demo_case
validation_status
```

Reject organism-specific BIO mechanism IDs such as `pleurotus_cellulose_degradation`.
