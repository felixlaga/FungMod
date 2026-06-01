# Dataset Candidate Reviews

This folder is for schema-first review records only. A candidate review names a
possible future dataset and records why it might be useful, what schema gates it
must pass, and what it must not be used for.

Candidate review files must not contain observations, measurement series, CSV
paths, extracted rows, calibrated parameters, or empirical model claims. Real
data insertion still belongs in `data/experiments/literature/` only after the
candidate is selected, the literature metadata schema passes, units and
uncertainties are explicit, and preprocessing is documented.

The current fake review fixture is a schema test only. It is not a dataset and
must not be interpreted as evidence.
