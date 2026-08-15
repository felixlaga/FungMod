# Literature Experiment Dataset Contract

This folder contains provenance-complete literature datasets plus the schema
contract and review checklist used before ingestion.

Current datasets:

- `alvarez_gonzalez_2022_free_beta_glucosidase/`: four nine-point digitizations
  of Supplementary Figure S1 in Alvarez-Gonzalez et al. (2022), covering both
  panels and both cellobiose loadings. All four are `literature_raw`, represent
  a purified commercial enzyme formulation of unstated biological source, and
  are suitable for bounded model comparison, not calibration or a general
  validation claim.

  - Figure S1A filled squares: 20 g/L cellobiose, 59.2 mg/L free enzyme. This is
    the original series and the reference condition for the held-out study.
  - Figure S1A open squares: 70 g/L cellobiose at the same enzyme loading.
  - Figure S1B filled squares: 20 g/L cellobiose at the panel-B enzyme loading.
  - Figure S1B open squares: 70 g/L cellobiose at the panel-B enzyme loading.

  The three added series are held-out conditions for out-of-sample comparison.
  Because all four come from one figure, one publication, and one laboratory,
  agreement across them demonstrates transfer across experimental conditions and
  must never be reported as independent experimental replication. The two
  panel-B records preserve an unresolved source unit inconsistency: the Figure S1
  caption prints the panel-A loading as 59.2 mg/L and the panel-B loading as
  296.1 mg/mL. The printed value and unit are stored verbatim and are not
  silently corrected.

  `scripts/digitize_alvarez_gonzalez_2022_figure_s1.py` regenerates the three
  added series. It verifies the supplementary PDF SHA-256 and refuses to write
  anything unless it first reproduces the committed Figure S1A filled-square
  series within the declared 0.6 mM digitization resolution.

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
tracked.

Fake metadata examples may live outside this directory, for example under
`data/experiments/literature_schema_examples/`. Those examples are schema tests
only. They are not empirical datasets and must not be interpreted as literature
evidence.

fake examples are schema tests only.
