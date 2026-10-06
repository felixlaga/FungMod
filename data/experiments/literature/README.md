# Literature Experiment Dataset Contract

This folder contains provenance-complete literature datasets plus the schema
contract and review checklist used before ingestion.

Current datasets: three enzyme-hydrolysis sources (seven series, four enzyme
preparations), one whole-culture source (six conditions, twelve biomass and
substrate series) and one colony-growth source (two species, sixteen
temperature-humidity conditions, sixty-four area and tip-count series).
Distinct publications do not establish matched independent validation of any
one model.

- `gelain_2020_t_harzianum/`: six machine-readable batch conditions for
  *Trichoderma harzianum* P49P11 from Gelain et al. (2020),
  DOI `10.1016/j.cesx.2020.100085`, dataset `10.17632/shd3wcczsr.2`, CC BY 4.0.
  Twelve biomass/substrate series contain 96 non-initial observations over
  8–96 h. `literature_processed`: source duplicate means with unavailable
  replicate errors, not raw replicate measurements. Initial-condition entries
  and activity assays remain in `../source_intake/gelain_2020/recorded_values.csv`.
  All six conditions were used for estimation in the original publication.
  The source's separate validation conditions were not found as observation
  workbooks in the deposited archive. Source `data.xlsx` files are simulations
  and are excluded. Regenerate with
  `python scripts/prepare_public_experimental_data.py`; verify with `--check`.
  These data add no validated fungus model or inferred physiological parameters.

- `alvarez_gonzalez_2022_free_beta_glucosidase/`: four nine-point digitizations
  of Supplementary Figure S1 in Alvarez-Gonzalez et al. (2022), covering both
  panels and both cellobiose loadings. All four are `literature_raw`, represent
  a purified commercial enzyme formulation of unstated biological source, and
  support bounded model comparison and explicitly labelled parameter estimation.
  They do not establish a general validation claim.

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


- `ariaeenejad_2020_persibgl1_cellobiose/`: a seventeen-point digitization of
  Figure 6 in Ariaeenejad et al. (2020), a 380 h cellobiose hydrolysis by the
  metagenome-derived PersiBGL1 at 40 C and pH 8. `literature_raw`. This source
  was previously blocked in `candidate_reviews/` on a time-axis conflict; the
  block was lifted from the figure's own x-axis label, which prints the unit
  directly. Two further source defects, a wrong y-axis unit and an anomalous
  tick label, are recorded rather than silently corrected. Regenerate with
  `scripts/digitize_ariaeenejad_2020_figure_6.py`.

  The paper's 1.25 mM Michaelis constant was measured using pNPG at pH 7;
  it is not a matched cellobiose constant for this pH-8 time course. The
  exploratory cross-source runner estimates cellobiose `K_m` from the curve
  and reports that local fit diagnostics do not establish identifiability.

- `cao_2015_bgl6_cellobiose/`: two six-point digitizations of Figure 5a in Cao
  et al. (2015), covering wild-type Bgl6 and the engineered mutant M3 hydrolysing
  10 % w/v cellobiose at 50 C and pH 6. `literature_raw`, CC BY 4.0. Two
  limitations are recorded: the publisher's largest figure rendition is only
  709 x 276 px, and the source's genuine standard-deviation error bars were not
  extracted, so the stored uncertainty is extraction resolution only. Regenerate
  with `scripts/digitize_cao_2015_figure_5a.py`.

- `de_ligne_2019_colony_growth/`: four `literature_processed` datasets from the
  supplementary figures of De Ligne et al. (2019), IMA Fungus 10:7, DOI
  `10.1186/s43008-019-0009-3`, CC BY 4.0: mycelial area (cm2) and number of
  hyphal tips of *Coniophora puteana* MUCL 11662 and *Rhizoctonia solani*
  AG4-HG-I S010-1 on an inert Petri-dish surface, hourly for 62 h, under all
  sixteen combinations of 15, 20, 25, 30 C and 65, 70, 75, 80 percent RH. Each
  dataset holds sixteen condition series (one CSV each) of the authors' means
  of four replicates with the plotted standard deviation where it could be
  read. Every condition is plotted twice in the source (in a temperature panel
  and in a humidity panel); both readings, their difference and a flag column
  naming every reading limitation (hidden markers, unreadable bars,
  single-panel values) are stored with each row, and the per-panel pixel
  coordinates are preserved in `../source_intake/de_ligne_2019/digitized_panels.csv`.
  Regenerate with `scripts/digitize_de_ligne_2019_figures.py`; verify with
  `--check`. The extractor verifies the source digests, the legend colour order,
  the axis fits and three prose statements of the article before writing.
  All sixteen conditions of a species come from one experiment and one figure,
  so agreement across them is within-study transfer and not independent
  replication. The intended use is the colony-expansion target of the spatial
  mycelium core under a frozen calibrate-and-hold-out plan; mycelial area and
  tip count are graph-derived image measures that need a declared observation
  operator before comparison with hyphal density fields.

Resa and Buckin (2011) remains blocked in `candidate_reviews/`: its full text is
paywalled and no extractable observations were found.

Because each source uses a different enzyme preparation, kinetic parameter
values are never transferred between sources. Cross-source work tests whether
one rate-law structure is adequate, not whether one parameter set is.

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
