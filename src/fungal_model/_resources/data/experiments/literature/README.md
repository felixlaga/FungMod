# Literature Experiment Dataset Contract

No real literature data are included yet. This folder is a schema contract and
review checklist only.

The machine-readable schema validation now exists in
`fungal_model.data.validate_literature_dataset_metadata`. Every future
paper-derived experiment dataset must pass that schema before it can be added
to this directory.

Before any paper-derived dataset is added, each literature dataset must record:

- citation;
- DOI or URL;
- authors;
- year;
- figure or table identifier;
- extraction method or tool;
- extracted_by;
- extraction_date;
- raw units;
- measurement definitions;
- uncertainty definitions, or a documented reason uncertainty is unavailable;
- measurement method;
- digitization metadata when values come from a figure;
- table metadata when values come from a table;
- supplementary-data metadata when machine-readable source files are used;
- unit-conversion notes;
- excluded points;
- preprocessing steps;
- preprocessing notes;
- source/provenance notes.

Allowed future literature maturity labels are:

- `literature_raw`;
- `literature_processed`.

Toy, synthetic, calibrated, and validated datasets must not be stored here.
Synthetic fixtures belong under `data/experiments/synthetic/`.

Adding a real paper dataset requires tests that load the dataset, verify the
metadata above, validate units and CSV columns, and confirm preprocessing is
tracked. Until those tests exist, this directory must contain no real paper
YAML or CSV files.

Fake metadata examples may live outside this directory, for example under
`data/experiments/literature_schema_examples/`. Those examples are schema tests
only. They are not empirical datasets and must not be interpreted as literature
evidence.

fake examples are schema tests only.
