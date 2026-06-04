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

The Resa and Buckin 2011 review is a real literature candidate that remains
blocked because public checks did not find ingestible observations or
supplementary data.

The Ariaeenejad 2020 PersiBGL1 review is a public open-access alternate
candidate with a specific cellobiose hydrolysis figure target. It is still a
review only: REAL-002F found unresolved source-text conflict in the Figure 6
time axis, so the figure has not been digitized and no extracted observations
have been added.
