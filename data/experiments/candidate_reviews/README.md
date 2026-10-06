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

The De Ligne 2019 review (`de_ligne_2019_colony_growth_review.yml`) names the
colony-expansion dataset selected for the spatial mycelium core: mycelial area
and tip counts of *Rhizoctonia solani* and *Coniophora puteana* under sixteen
temperature and humidity conditions, IMA Fungus 10:7, CC BY 4.0. It is
`selected_for_schema_review`: the article and its additional files are still to
be committed under `../source_intake/de_ligne_2019/` with digests before the
literature schema can be checked and any series extracted.
