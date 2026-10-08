# Changelog

All notable public releases of FungMod are documented here.

## [Unreleased]

### Added

- A walkthrough from a fungus name to a simulation (DOCS-WALK-001):
  `docs/walkthrough.md` runs `fungmod assemble --fetch-proteome
  --fetch-kinetics --network`, resolves the draft's conflict with
  `--entry-id`, fills its `REVIEW:` fields, then `fungmod check-data` and
  `fungmod run --runnable-only` (exit codes 0, 3 and 4), reads the metrics,
  rates, threshold times, provenance, limitations and measurement requests,
  and shows how your own measurements replace the transferred estimates.
  Every output shown is real output on frozen snapshots of the existing
  synthetic UniProt and SABIO-RK test responses
  (`tests/fixtures/walkthrough/`, said on the page to be synthetic, not
  biology); `tests/test_walkthrough_doc.py` reruns every command shown and
  checks every line shown, so the page cannot drift. New
  `scripts/verify_live_sources.py` checks, once, on a machine with internet
  access, the live UniProt proteome search, UniProtKB export and SABIO-RK
  EC-number query through FungMod's own query builders, parsers and snapshot
  checks, and reports per endpoint the URL, HTTP status, the headers FungMod
  relies on, the columns or fields found against those expected, the entries
  and every mismatch (exit code 1 on a mismatch, 3 when an endpoint could not
  be checked); it writes only to a new temporary directory or an
  `--output-dir` outside the repository. Its tests run it offline with
  patched `urlopen`. No scientific or numerical behaviour changed; the live
  formats remain unverified until the script is run against the services.

- Kinetics of the fungus's enzyme classes looked up in SABIO-RK by EC number
  (FETCH-002): `assemble_user_tables(fetch_kinetics=True)` and `fungmod
  assemble --fetch-kinetics` query SABIO-RK's kinetic-law export once per
  complete EC number of each registry class of the repertoire that acts on a
  requested substrate (with `network=True`, on a pool), its EC number and the
  EC-number aliases the registry resolves to it, restricted to the
  substrate's name: `ECNumber:"<EC number>" AND Substrate:"<substrate name>"`
  (the existing discovery query builder; never a name guess, never broader).
  Each answer is frozen in the existing SABIO-RK snapshot layout of
  `fetch_and_save_export` (raw pages, combined export, `fetch_metadata.json`
  with query, URLs, retrieval time, HTTP status, `total_count` and SHA-256)
  and verified on every read (`fungal_model.sources.sabiork.query_snapshots`).
  SABIO-RK is reached only with `refresh=True` (`--fetch`, the command line's
  one network opt-in); without it only the snapshots are read, every missing
  one is refused together with the command that fetches it, and the same
  command gives the same draft byte for byte. An HTTP error, an answer that is
  not the export envelope, and an answer whose entries do not add up to its
  `total_count` (truncated or incompletely paginated; every page is fetched)
  store nothing; a changed snapshot, two snapshots of one query, and a new
  answer whose bytes differ from the stored one are refused and the snapshot
  kept, with the directory to remove. The looked-up entries join the kinetics
  sources and follow the existing per-case rules (own species literature,
  other organisms transferred estimates, conflicts, gaps, no reuse across
  conditions without a law; `entry_ids` and `same_species` across local and
  looked-up entries). Classes without an EC number, classes of a user dataset
  (the SABIO-RK conversion resolves EC numbers against the registry only),
  substrates whose categories are `REVIEW:` fields and unquotable names are
  listed and not queried. The report gains `assembly["kinetics_lookup"]`
  (every query with its snapshot, the entries converted and the cases they
  feed, every other entry with its use, reason and unconverted parameters,
  and what was not queried); `review.md` a "Kinetics looked up by EC number"
  section; the command line prints the same per query. New exceptions
  `KineticsLookupError`, `MissingKineticsSnapshotError` and
  `KineticsSnapshotConflictError` (subclasses of `UserTablesAssemblyError`).
  The query form, its fields and SABIO-RK's answer to a query without matches
  were not verified against a live response; the tests serve synthetic
  responses (`tests/fixtures/sabiork_kinetics_queries/`). Without
  `fetch_kinetics` drafts are byte-identical to the previous version (pinned
  digests).

- Enzyme-network links across amount bases through a stated, unit-bearing
  yield (NETWORK-002): in a network dataset a solid pool (dry mass per volume)
  may release a dissolved pool (amount per volume), or a molar final product,
  when its `substrates.csv` row states `yield_basis` as an amount of product
  per dry mass (for example `mmol/g`, checked with pint) with the new optional
  columns `yield_evidence_type` (`measured`, `literature`, `estimate`) and
  `yield_method` (required for measured and literature values). The yield
  becomes a parameter record per strain and condition (role
  `product_yield__<pool>`) bound to the release coefficient, so its evidence
  sets the mode like any other input; FungMod never derives it from a molar
  mass or a registry product map. Pools after the basis change are reported in
  the entry's units times the yield's, simplified by pint (g/L x mmol/g =
  `millimole / liter`); the closure ledger weighs the solid through the yield
  (`{value, units}` weights, checked in pint) and `final_product_yield` keeps
  its units across bases (`millimole / gram`). Core generalisation, generic and
  opt-in: `ProductReleaseMap.coefficient_units`, unit-bearing product
  coefficients in `HomogeneousMichaelisMentenProcess`
  (`product_coefficient_units`, `product_state_units`; the compiled core
  converts them once at build time), unit-bearing `parameter_role`
  coefficients and closure weights in the composition builder, initial-state
  `units_from_roles` on case templates, and `conserved_weight` in the
  validators; the surface-catalysis and transglycosylation processes, the
  factories of those and of the pH-ionization process, and the SBML exporter
  refuse a unit-bearing coefficient instead of reading it as a pure number. Refused with file, row and column: a
  dry-mass-to-amount link without such a yield, a unit-bearing yield on a link
  between two solids, of the wrong dimension, on a dissolved row or outside a
  network, a dissolved pool releasing a solid one, and missing or misplaced
  yield evidence. Fixtures `network_solid_chain` (a cellulose-like solid in g/L
  -> a disaccharide-like pool in mmol/L -> a monomer-like product, competitive
  inhibition) and `network_solid_parallel` (two classes on a chitin-like solid
  -> a dimer-like product in umol/L); illustrative estimates only. Every
  existing registry case and user fixture assembles byte-identically (pinned
  config and record digests) and its outputs are unchanged.

- An enzyme network drafted for a fungus, substrates and conditions
  (ASSEMBLE-002): `assemble_user_tables(network=True)` and `fungmod assemble
  --network` draft the USERDATA-010 `enzyme_network` block with the requested
  substrates as entry substrates, follow the pools each releases only through
  stated products (the request's `product`, the user dataset's `substrates.csv`
  row, or a registry record's single product) that equal a `substrate_id` of
  the user dataset or a registry substrate ID (never a name; such a pool is
  added as an intermediate), and make every class of the repertoire
  (annotation, proteome export, asserted classes, registry record, user
  dataset) that acts on a pool a member, with the existing per-case kinetics
  status (own, same-species literature, cross-organism transfer as an
  estimate, conflict, gap). A member without kinetics is a gap with the
  existing measurement requests, never a dropped class. The loader's network
  rules are applied while drafting: intermediate pools take no initial
  concentration (such rows are listed), an entry has one per condition (the
  user's rows win; disagreeing source values become one `REVIEW:` field;
  `design` is written once per entry and condition), the pH-ionization form is
  a gap with the reason, and refused with the reason are `responses`, a
  dataset's `responses.csv` rows on a pool, cycles, ambiguous products,
  products that are solid substrates, a class on two pools of one network, an
  entry no class acts on, colliding state names and disagreeing user initial
  concentrations. The report gains `assembly["network"]` (pools, links, final
  product, members and their status per condition, classes acting on no pool,
  and per condition `all_members_have_kinetics`, `blocked` with what blocks
  it, or `undetermined`) and `network_role` on substrates; `review.md` an
  "Enzyme network" section; a network draft's `kinetics.csv` the `inhibitor`
  column; `fungmod assemble --network` prints the network block and a `run`
  command with `--runnable-only` when a network case is blocked. A network
  dataset is accepted as `user_data` with `network=True` (its `ki` rows kept).
  Without `network` drafts are byte-identical to the previous version (pinned
  digests).

- A software-only paper draft for the Journal of Open Source Software,
  `paper/joss/paper.md` with its bibliography (PAPER-003): no research
  results, the journal's 2026 sections, author statements still to be
  completed; a workflow builds its PDF with the journal's toolchain and
  `tests/test_joss_paper.py` checks its sections, citations and length.

- Several enzyme classes acting together in user data (USERDATA-010): an
  optional `enzyme_network` block in `user_dataset.yml` (`entry_substrates`)
  makes every case of the dataset an enzyme network instead of the one class
  the preflight selects. Every declared class of the strain that acts on a
  pool of the network runs its own homogeneous Michaelis-Menten process (kcat
  or Vmax form, every existing route to Vmax and to the enzyme concentration);
  processes on one pool add their rates, and a pool released by one class is
  the next class's substrate only where a substrate's `substrates.csv`
  product equals another `substrate_id`, with the stated yield. Intermediates
  and the final product start at zero; every pool is reported in the entry's
  units; closure weights come from the yields. A new `kinetics.csv` quantity
  `ki` with a new column `inhibitor` (a downstream pool) binds the existing
  provenance-bound `competitive_inhibition` modifier,
  `Vmax S / (Km (1 + I / Ki) + S)` with the process's own Km; a process
  without `ki` has no inhibition term and says so in its template. No new
  numerics: a new `enzyme_network` template type is assembled by the
  `culture_physiology` composition builder, generalised to
  `build_composed_process_config_data` (which now also binds the existing
  `competitive_inhibition` and `substrate_reactivity` modifiers and records
  each process's enzyme class as output metadata); the shipped culture case
  assembles byte-identically. Records are selected per case (strain, entry,
  condition); every missing role is a gap with the single-class measurement
  request, and a network with a gap is not simulated. Refused with file, row
  and column: cycles, ambiguous products, links between dissolved and
  dry-mass pools, a class on two pools of one network, strains with different
  member classes, inputs of intermediate pools, disagreeing entry loadings,
  the pH-ionization form, `culture.csv`, `timecourse.csv` and `responses.csv`
  in a network dataset, `ki` outside a network, on a solid, in mass units, on
  a non-downstream pool or with two inhibitors per process, and a network
  dataset as `user_data` of `assemble_user_tables`. `UserDataset.enzyme_networks`
  (and `to_dict()`/`summary()`) lists each network; `fungmod check-data` prints
  them; `mechanism_summary.csv` gains one process-law row per network process
  (naming its class) and a row per competitive-inhibition modifier (output
  schema unchanged, 2.2.0). Fixtures `network_chain` (polymer-like ->
  oligomer-like -> monomer-like, two classes) and `network_parallel` (two
  classes in parallel, kcat and Vmax forms, one competitively inhibited);
  illustrative estimates only. Datasets without `enzyme_network` generate
  byte-identical records.

- A fungus's enzyme repertoire from its name (FETCH-001): `fungmod assemble
  --fetch-proteome` searches UniProt's reference proteomes for the name of
  `--scientific-name` (or, without it, of `--fungus`) and takes a proteome
  only when exactly one candidate's organism name equals it
  (case-insensitive) or the search has a single candidate; no candidate,
  several without one exact match, or a truncated search is refused (exit 2)
  with every candidate listed (identifier, organism, taxonomy id, type,
  protein count), and `--proteome UP...` chooses one (among the candidates
  when `--fetch-proteome` is kept; any proteome without it). The chosen
  proteome's UniProtKB export is copied into the draft and written as its
  `genomes.csv` row (`UniProt release <X-UniProt-Release>`, or the retrieval
  date recorded as such when the header is absent; the source names the
  organism, taxonomy id, query, SHA-256 and URL), and the classes come from
  the existing UniProt route; no kinetic value comes from a proteome.
  `--fetch` is the command line's only network opt-in: without it the frozen
  snapshots under `--snapshot-dir` (default `data/source_snapshots/uniprot`)
  are read and verified, the same command reruns offline byte for byte, and a
  missing snapshot is refused with the command that fetches it; a changed
  snapshot, or a new response that differs from a stored one, is refused.
  `--annotation` and the proteome options are refused together.
  `fungal_model.sources.uniprot` adds `search_proteomes_by_name` (the search
  response frozen with URL, query, retrieval time, HTTP status, release and
  result-count headers and SHA-256), `choose_proteome`,
  `resolve_proteome_name`, `fetch_proteome_by_name` (which also checks the
  export's taxonomy id against the chosen candidate's),
  `parse_proteome_search_tsv` and the error types `ProteomeChoiceError`,
  `MissingSnapshotError` and `SnapshotConflictError` (both subclasses of
  `UniprotFetchError`, raised where it was raised before).
  `assemble_user_tables` takes `proteome` (a frozen proteome snapshot) and
  `proteome_selection` (how it was chosen, recorded in `user_dataset.yml`,
  `review.md` and the assembly report), and reads `annotation` as a UniProtKB
  TSV export when `annotation_tool` names UniProt. The proteomes search
  endpoint, the query fields `organism_name` and `proteome_type` and the
  columns `upid`, `organism`, `organism_id` and `protein_count` are used as
  UniProt documents them; they were not verified against a live response,
  because the development environment could not reach rest.uniprot.org, and
  the tests use synthetic responses
  ([from a fungus name](docs/user-data.md#from-a-fungus-name)).

- Fungal cultures in user data (USERDATA-009): "fungus X on substrate Y in
  conditions Z" now also simulates the fungus growing on the substrate and
  secreting its enzymes, not only an enzyme at a stated concentration. An
  optional `culture.csv` binds the registry's existing `culture_physiology`
  composition (the *T. harzianum* P49P11 case's model: substrate consumption
  `k_h E S / (K_h + S)` by one enzyme pool, biomass with an explicit yield
  and a closure ledger, first-order biomass loss, and biomass-proportional,
  substrate-induced synthesis and first-order loss of every enzyme pool) to a
  user's strain and solid substrate, one row per role and condition:
  `substrate_initial_concentration`, `initial_biomass`, `biomass_yield`,
  `biomass_loss_rate`, `induction_half_saturation` (culture level),
  `hydrolysis_capacity`, `hydrolysis_half_saturation` (the consuming pool)
  and `initial_enzyme_concentration`, `specific_production_rate`,
  `enzyme_loss_rate` (each pool). Units are checked with pint per role and per
  case (`k_h x E` and `q x X` against the case's own pool and biomass units;
  substrate and biomass in one unit); pools stay a protein mass or an assay
  activity and are never converted; maturity follows the evidence type (the
  weakest input wins); every missing role is a gap whose measurement request
  names it in plain words; nothing is defaulted. One culture model per
  consuming class and solid substrate is generated (template, compatibility,
  records for every strain declaring the class); `UserDataset.cultures`, its
  `summary()` and `to_dict()` list them, and `fungmod check-data` prints them.
  Refused with file, row and column: a culture on a dissolved substrate,
  culture rows mixed with enzyme-assay rows for the same strain and substrate
  (or for the culture's class and substrate, or for the culture's class
  anywhere), a strain with a second class acting on the culture substrate or
  missing a pool, no or two consuming pools, response laws and time courses
  of culture cases, units of the wrong dimension and `fitted` evidence.
  `assemble_user_tables` and `fungmod assemble` do not draft cultures: the
  solid-substrate refusal names the culture. No new numerics: re-entering the
  registry case's records (`tests/fixtures/user_data/culture_reentry`)
  reproduces its trajectories at every loading, and the shipped case
  assembles byte-identically
  ([fungal culture](docs/user-data.md#fungal-culture-growth-and-secretion)).

- Registry records for xylan, starch and chitin and their hydrolase classes
  (REGISTRY-002), categorical metadata without kinetic values. Enzyme classes
  `endo_xylanase` (EC 3.2.1.8; aliases `endo-xylanase`, `endoxylanase`,
  `xylanase`), `glucoamylase` (EC 3.2.1.3; `glucan 1,4-alpha-glucosidase`,
  `amyloglucosidase`) and `chitinase` (EC 3.2.1.14; `endochitinase`), the ids
  the CAZy family map already assigns to GH10/GH11, GH15 and GH18; provenance
  IUBMB (ExplorEnz) and CAZy (Drula et al. 2022), maturity
  `literature_metadata`, process `homogeneous_michaelis_menten` only. Solid
  substrates `xylan` (`beta_1_4_xylosidic`), `starch` (`alpha_1_4_glycosidic`,
  `alpha_1_6_glycosidic`, categorical; no branch-point model) and `chitin`
  (`beta_1_4_n_acetylglucosaminidic`), `physical_state` `solid_polymer`,
  generic polysaccharide definitions (`exploratory_metadata`; composition
  varies by source and is not recorded), declaring the products
  `D_xylose_equivalent`, `beta_D_glucose` and
  `N_acetyl_D_glucosamine_equivalent` (monomer equivalents where the enzyme
  releases oligosaccharides). The first records of
  `data_registry/product_maps/product_maps.yml`: the complete-hydrolysis mass
  yields 1.136358, 1.111107 and 1.088659 g/g of the idealized homopolymers,
  with the formula from conventional atomic weights in their provenance;
  reference stoichiometry that no route fills or checks a user's yield from.
  A user dataset can reference the three polymers as registry substrates and
  run user kinetics on them through the apparent Michaelis-Menten route of
  USERDATA-008 ([registry polymers](docs/user-data.md#registry-polymers)).
  GH10, GH11, GH15 and GH18 genes of a dbCAN annotation and EC 3.2.1.8,
  3.2.1.3 and 3.2.1.14 proteins of a UniProt export now resolve to modellable
  classes instead of `unmodellable_enzyme_classes`; on a dataset substrate that
  references the polymer their roles are gaps with dry-mass measurement
  requests. No compatibility record, case template, parameter record or
  family-map change; no LPMO or endoglucanase record. The UniProt format
  fixture gains `X0TEST13` (AA1, EC 1.10.3.2), so a class without a record
  stays covered.

- Partial runs: simulate the runnable cases of a request and report the
  blocked ones (RUN-001). `VirtualExperiment.simulate(..., blocked="report")`
  simulates exactly the cases whose preflight allows simulation in the
  requested mode (`preflight_policy`; scientific mode: `modelable` only) and
  lists the others as not simulated; the default `blocked="refuse"` refuses
  the request as before, and a request without any runnable case is refused
  identically under both. Blocked cases get rows in
  `modelability_preflight.csv`, `modelability_items.csv`,
  `missing_parameters.csv`, `suggested_experiments.csv`,
  `assumption_summary.csv`, `limitations_table.csv` (a blocking
  `not_simulated` row) and `case_summary.csv`, and none in the per-sample
  tables. Output schema `2.2.0` adds `case_summary.csv` columns `case_status`
  (`simulated`, `not_simulated`) and `not_simulated_reason`;
  `virtual_experiment_summary.json` and `output_manifest.json` gain
  `blocked_policy`, `partial_run`, `requested_case_count`,
  `simulated_case_count` and `blocked_cases`; the report states a partial
  run. `DegradationScreenResult` gains `blocked_policy`, `blocked_reports`,
  `partial_run` and `blocked_cases()`. `simulate_screen(..., cases=...)`
  simulates listed triples of the requested grid in the order given; every
  case keeps its grid position (`RegistryCaseEnsemble.case_index`, the
  `case_<position>` id) and the seed of that position, so its samples are the
  same in a full run, a partial run and a one-case selection of the same
  request. `fungmod run --runnable-only` is the command-line form: it lists
  the blocked cases with their measurement requests and exits with the new
  code 4 (partial run); without the flag the exit code stays 3, and the
  message suggests the flag when some case is runnable. `fungmod assemble`
  prints its `run` command with `--runnable-only`, and says why, when a case
  of the draft is a gap or a conflict
  ([command line](docs/cli.md#run-the-runnable-cases-of-a-request),
  [partial runs](docs/concepts/outputs.md#partial-runs)).

- The user-data workflow from the command line (CLI-002), so that "fungus X
  on substrate Y in conditions Z" runs end to end from a shell:
  `fungmod assemble` (`assemble_user_tables`: one `--fungus`, `--substrate`,
  a `--temperature-c` x `--ph` grid, `--annotation` with `--annotation-tool`
  and `--annotation-source`, `--enzyme-class` and `--enzyme-class-evidence`,
  `--kinetics-source`, `--entry-id`, `--same-species`, `--user-data`,
  `--responses` CSV, `--design QUANTITY=VALUE UNITS`, `--time-grid`,
  `--cache-dir`, `--dataset-id`, `--output`) writes the draft and prints the
  per-case report (class, substrate, condition, kinetics status, route,
  source ids, reason), the `REVIEW:` fields as `file:row:column: note` and
  the next `check-data` and `run` commands (with a grid command for a
  law-carried condition); `fungmod draft-kinetics SOURCE --provider sabiork`
  (`user_tables_from_sabiork` on an export file or a frozen snapshot) prints
  the converted entries and every entry and parameter not converted with the
  reason; `fungmod fit DIR --case ... --fit QUANTITY LOWER UPPER UNITS`
  (`fit_user_dataset`, every keyword mapped) prints fitted values, intervals,
  identifiability verdicts and the in-sample claim boundary and writes the
  fitted dataset, and exits with code 2 when the API refuses the fit (an
  unidentified quantity unless `--allow-unidentified`); `fungmod run
  --compare-timecourses` (`DegradationScreenResult.compare_with_timecourses`)
  writes `timecourse_comparison.csv` and prints RMSE, mean residual, band
  coverage and observations used in a fit per series; `fungmod check-data`
  also prints the genome or proteome resolution, the time courses, the fit
  block of a fitted dataset and a hint after unfilled `REVIEW:` fields. No
  subcommand fetches. `USER_TABLE_PROVIDERS` in
  `fungal_model.api.user_data_sources` maps the provider name `sabiork` to
  `user_tables_from_sabiork`, so that the command line names no source
  database (`docs/cli.md`). The printed next-step commands quote their
  arguments for the platform's shell (POSIX quoting, or the double quotes
  `cmd` and PowerShell read on Windows).

- Solid substrates in user data (USERDATA-008): a `substrates.csv` row may
  declare one suspended solid polymer, `physical_state` `solid_polymer` with
  the new column `amount_basis` `dry_mass` and `yield_basis` `g/g`; a registry
  substrate whose record is `solid_polymer` may be referenced the same way. The
  existing homogeneous Michaelis-Menten law then runs as an apparent bulk law
  on the dry mass per volume (kcat or Vmax form; the law of the registry's
  culture-physiology hydrolysis process), with the enzyme as a protein mass or
  an activity in one of the registry's assay units per volume and `kcat`
  checked per case with pint so that `kcat x E` is the substrate's mass per
  volume per time. New `kinetics.csv` quantities: `enzyme_dose` (enzyme per
  dry substrate mass; times the case's exact `substrate_initial_concentration`
  it is one derived enzyme-concentration record listing both rows, the formula
  and the pint factor, at the weaker input's maturity; mixing it with an
  explicit `enzyme_concentration` or a ranged initial substrate is refused) and
  `reactivity_exponent` (binds the existing `substrate_reactivity` modifier,
  `(S/S0)^n` with `S0` the case's own initial-substrate record, citing the
  modifier's Kadam et al. 2004 provenance; refused on dissolved substrates).
  Refused on solids, each with file, row and column: the specific-activity,
  enzyme-loading and assay-activity routes to Vmax, the pH-ionization form
  (also an ionization class acting on a solid), molar units, composite
  (`mixed_solid`, `solid_biomass`) and `unknown` states, adsorption,
  binding-capacity and surface-area quantities and columns, and time courses.
  Generated templates state the apparent-law limitations (no adsorption or
  partitioning, surface law, synergy, product inhibition or LPMO kinetics).
  Scientific mode follows the unchanged rule. The assembly route refuses a
  requested solid substrate of a user dataset. New fixture
  `tests/fixtures/user_data/solid_case/` (`docs/user-data.md#solid-substrates`).

- Registry enzyme class `cellobiohydrolase` (USERDATA-008): EC 3.2.1.91 with
  the reducing-end EC 3.2.1.176 as an alias, target bond class
  `beta_1_4_glycosidic`, substrate classes `cellulose_particulate` and
  `cellulose_film_generic`, compatible process `homogeneous_michaelis_menten`;
  provenance IUBMB (ExplorEnz) and CAZy GH6/GH7 (Drula et al. 2022), maturity
  `literature_metadata`, no kinetic values. GH6/GH7 genes of a dbCAN
  annotation and GH7 or EC 3.2.1.91/3.2.1.176 proteins of a UniProt export now
  resolve to a modellable class instead of `unmodellable_enzyme_classes`; on a
  solid cellulose substrate its roles are gaps with measurement requests, and a
  GH7 protein annotated with another class's EC number is a disagreement on
  both classes. The CAZy family map is unchanged; endoglucanase and LPMO have
  no record.

- One reviewable dataset for "fungus X on substrate(s) Y at condition(s) Z"
  (ASSEMBLE-001): `assemble_user_tables` drafts the user-dataset tables for
  exactly that request from the sources at hand (a dbCAN annotation copied into
  the draft and listed in `genomes.csv`, enzyme classes the user asserts, the
  registry record of a registry fungus, an existing user dataset, SABIO-RK
  entries as `user_tables_from_sabiork` accepts them) and returns an
  `AssembledTablesDraft` (a `UserTablesDraft` with `responses.csv`,
  `genomes.csv`, the annotation file and an `assembly` report). Per enzyme
  class, substrate and condition the report and `review.md` give the class
  evidence, the kinetics status (`user_data`, `literature_same_organism`,
  `transferred_estimate`, `conflict`, `gap`), how the condition is reached,
  the source IDs and the reason. The repertoire comes only from the
  annotation, asserted classes, the fungus's dataset rows or its registry
  record; classes acting on a substrate without evidence are reported and not
  added; SABIO-RK entries of the fungus's species are converted by
  `user_tables_from_sabiork` (literature), entries of another organism by the
  same conversion and then written as `estimate` rows whose method begins
  "transferred from <organism> enzyme, SABIO-RK entry <id>"; several
  candidates for one case are listed until `entry_ids` chooses; kinetics are
  never reused at another condition, except through a temperature or pH law
  at an `EnvironmentGrid` condition, which the report names. The reviewer,
  time grid, kcat-form enzyme concentration, unsettled yields, new substrate
  categories and the annotation source are `REVIEW:` fields unless given.
  Nothing is fetched, and the output is byte-identical for the same input
  (`docs/user-data.md#assembling-fungus-substrate-and-conditions`).

- pH-ionization kinetics in user data (USERDATA-006): a third rate form for a
  (class, substrate) pair in `kinetics.csv`, with the quantities
  `kcat_limiting` (1/time), `km_limiting` (concentration), `pk_free_lower`,
  `pk_free_upper`, `pk_complex_lower`, `pk_complex_upper`, `ph_min` and
  `ph_max` (dimensionless) beside `substrate_initial_concentration` and
  `enzyme_concentration`. They map to the roles of the existing
  `ph_ionization_michaelis_menten` assembler exactly as the registry's BGL1A
  records do (`turnover`, `michaelis_constant`, the four pK roles,
  `minimum_ph`, `maximum_ph`), and each pair gets a `..._ph_ionization_mm`
  compatibility and case template, gap records and measurement requests like
  the other forms. Mixing this form with the kcat or Vmax form in a case or a
  pair is refused, and so is an enzyme class that uses it on some substrates and
  another form on others. Validation: finite pK values, each lower pK below its
  upper pK (whole ranges for sampled pK values), exact `ph_min < ph_max` within
  0 to 14, and an exact condition pH inside `[ph_min, ph_max]` for every
  condition with pH-ionization rows; a pH response law from `responses.csv` on
  such a pair is refused as double-counting. `user_tables_from_sabiork` now
  drafts SABIO-RK entries of the diprotic "Michaelis-Menten (pH-dependent)"
  law (recognised by formula and parameter names) in this form, with `ph_min`
  and `ph_max` from the pH range the entry states (`REVIEW:` fields otherwise)
  and the condition pH a `REVIEW:` field when SABIO-RK gives a range; the
  `review.md` "pH-ionization laws" section no longer reports them as not
  importable, and their limiting constants are no longer written as `km` and
  `kcat`. New fixture `tests/fixtures/user_data/bgl1a_ph_ionization/` re-enters
  SABIO-RK entry 38522 and reproduces the registry BGL1A trajectory at pH 5
  (`docs/user-data.md#three-rate-forms`).

- Enzyme repertoire from a UniProt proteome in user data (USERDATA-007): a
  `genomes.csv` row with `annotation_tool` `UniProt` followed by the release or
  download date (a missing version is refused) points a strain to a UniProtKB
  TSV export inside the dataset directory, under the path rules of a dbCAN row;
  its bytes enter the dataset digest and `min_tools_agreeing` is refused on it.
  `fungal_model.capability.parse_uniprot_tsv` reads UniProt's own columns
  (`Entry` required; `EC number` or `CAZy`; `Entry Name`, `Protein names`,
  `Gene Names`, `Organism`, `Organism (ID)`, `Reviewed` optional; other
  columns ignored and listed), keeps partial EC numbers partial and refuses
  missing columns, repeated accessions, malformed cells and more than one
  organism per file. `resolve_uniprot_proteome` resolves each protein's CAZy
  families through the existing `CapabilityResolver` and family map and its
  complete EC numbers through `RegistryResolver.resolve_enzyme_class`; a
  protein whose two annotations name different classes (compared on the
  classes the EC side can speak about) supports no class and is listed in
  `ec_cazy_disagreements` with both sides. Classes with a registry record join
  the strain, others go to `unmodellable_enzyme_classes`; unmapped families,
  unresolved and partial EC numbers are listed. No rate is taken from the
  proteome; gap requests name the proteome, the accessions, the families, the
  EC numbers and how many entries are reviewed. UniProt entries in the dataset
  lists and `user_dataset_genome_resolution.json` carry `source_type`
  `uniprot_proteome` and accessions; dbCAN entries are unchanged.
  `fungal_model.sources.uniprot` builds the UniProt REST stream URL for a
  proteome or taxonomy id, fetches only with `refresh=True`, stores a
  SHA-256-checked snapshot with URL, query, retrieval time and release headers,
  refuses to overwrite a snapshot with a different digest unless asked, and
  copies the TSV into a dataset with a suggested `genomes.csv` row; the REST
  field names were not verified against a live response
  (`docs/user-data.md#from-a-uniprot-proteome`).

- Time courses in user data, comparison and fitting (USERDATA-004): an
  optional `timecourse.csv` (`strain_id`, `enzyme_class`, `substrate_id`,
  `condition_id`, `observable` = `substrate` or `product`, `time`,
  `time_units`, `value`, `units`, optional `sd` and `replicates`, `source`,
  `method`) is validated (declared references, amount-per-volume units of the
  case's kind, finite values, nonnegative times, one unit and one row per time
  in a series) and kept on `UserDataset.timecourses` by generated case id,
  never as registry records. `compare_with_timecourses` (also
  `DegradationScreenResult.compare_with_timecourses()`) interpolates the
  simulated median and 5-95 % band linearly to the observed times, refuses
  observations outside the simulated range, and writes
  `timecourse_comparison.csv` with residuals, RMSE, the fraction inside the
  band, observations with sd and an in-sample, not-validation note; output
  schema `2.1.0` adds the table. `fit_user_dataset` fits `km` with `kcat` or
  `vmax` of one case across conditions of one temperature and pH with
  `fit_least_squares` on the assembled model (compiled core), with required
  bounds, sd-weighted residuals (or an explicit, recorded
  `error_model="unweighted"`), a profile-likelihood identifiability verdict
  with bisected interval limits (local information for the unweighted
  objective), refusal of unidentified quantities unless
  `allow_unidentified=True`, and returns a new dataset (`UserDatasetFit.write`)
  whose fitted values are `kinetics.csv` rows of the new evidence type
  `fitted` (maturity `user_fitted`, exploratory screening only, refused by
  scientific mode), described by a manifest `fit` block and `fit_report.json`
  and checked on load. `profile_likelihood` gains an optional `diff_step`
  passed to its nuisance refits; `fungal_model.screening` gains
  `resolve_screen_role_records` (`docs/user-data.md`).

- Colony comparison stage 0 recorded (COLONY-002) under the plan's third
  dated amendment, before any fit: the radial domain ends at a 9 cm dish wall
  (a declared assumption), the 40 mm scan window is declared separately, and
  the symmetry check compares the radial model with a 0.25 mm cartesian
  reference over the hours before the radial tips reach the window walls.
  Grid (4.0e-5, 0.0054), solver (1.7e-8) and symmetry (0.026, 0.016 against
  0.03) checks passed; the two superseded stage 0 records are kept as the
  evidence for amendments 2 and 3. `tip_fraction_beyond_radius` and the
  plan-declared window and symmetry window in the study module. No fit.

- Public kinetics into user tables (USERDATA-005): `user_tables_from_sabiork`
  drafts the user-dataset tables (strains, enzymes, optional enzyme classes,
  substrates, conditions, kinetics) and a `user_dataset.yml` from SABIO-RK
  kinetic-law entries given as a `RegistryProposal` from `source_proposal`, a
  downloaded export JSON or a reaction ID read from the local snapshots;
  nothing is fetched while drafting. `UserTablesDraft.write` adds a
  `review.md` listing every mapping decision and every entry or parameter not
  converted, with the reason, and writes byte-identical files for the same
  input. One strain per organism and expression host (or
  `strain_id_for_organism`); EC numbers resolved against the registry (an
  unresolved one is listed, and an `enzyme_classes.csv` row with `REVIEW:`
  bond and substrate classes is drafted only with
  `propose_enzyme_classes=True`); substrates resolved by name or alias, product
  and mol/mol yield from the reaction stoichiometry; one condition per
  temperature and pH with the buffer in notes; Km, kcat, Vmax (as `vmax` or
  `specific_activity` by dimension) and the assay concentrations copied as
  `literature` values with `sd`, source (EntryID, first author, year, PubMed
  ID) and method (kinetic law), units kept when the unit registry parses them
  or mapped through the explicit `SABIORK_UNIT_SPELLINGS` table, otherwise
  listed. Mutant enzymes, isoenzyme conflicts on one case, kcat/Km, pKa and
  other parameters are listed, not converted; laws with pKa parameters are
  listed as pH-ionization laws and only their Km and kcat are converted. The
  `design` argument states the virtual assay's substrate and enzyme
  concentrations and enzyme loading. `load_user_dataset` now refuses any table
  cell or manifest value beginning with `REVIEW:`, naming each such field,
  before interpreting the tables; the simulation time grid of a draft is such
  a field (`docs/user-data.md#starting-from-sabio-rk`).

- Enzyme repertoire from a genome annotation in user data (USERDATA-003): an
  optional `genomes.csv` (`strain_id`, `annotation_file`, `annotation_tool`,
  `source`, optional `min_tools_agreeing`) points a strain to a dbCAN
  `overview.txt` inside the dataset directory (absolute and escaping paths,
  missing files, other tools, a tool without its version and malformed headers
  are refused; the file's bytes enter the dataset digest). The annotation is
  resolved with the existing `CapabilityResolver` and CAZy family map against
  the base registry: classes with a registry record join the strain's declared
  classes with the evidence "genome annotation (dbCAN, N genes, families ...)"
  (an explicit `enzymes.csv` row wins and keeps both pieces of evidence),
  classes without a record are listed in `unmodellable_enzyme_classes` and
  families without a class in `unmapped_families`, never turned into records.
  No rate is taken from the genome: every resolved class that can act on a
  dataset substrate but has no kinetics becomes `user_dataset_gap` unknowns
  whose measurement requests name the families the class was inferred from. The default consensus rule is the
  existing one of `families_from_overview` (a family called by any tool
  column); `min_tools_agreeing` requires that many tool columns per gene. The
  lists appear in `UserDataset.to_dict()`, the new `UserDataset.summary()`,
  `virtual_experiment_summary.json` and a `user_dataset_genome_resolution.json`
  written beside the preflight report. `fungal_model.capability` gains
  `parse_overview` (per-gene calls) and `default_family_map_path`; the family
  map's two citations containing a colon are now quoted so they load as text
  (`docs/user-data.md`).

- Vmax, activity and environment responses in user data (USERDATA-002):
  `kinetics.csv` accepts `vmax` (with a required `method`),
  `specific_activity`, `enzyme_loading` and `assay_activity` with the new
  columns `activity_substrate` and `activity_saturating`. Vmax comes from
  exactly one route per case: an explicit row, `specific_activity` x
  `enzyme_loading` (a derived record, computed with pint, listing both rows and
  the formula, with the weaker input's maturity in the order
  `exploratory_prior` < `user_design_value` < `user_reported_literature` <
  `user_measured`), or an assay activity on the case substrate at saturation;
  other substrates, sub-saturating activities, mixed routes and kcat with Vmax
  are refused. The homogeneous Michaelis-Menten assembler gains a generic
  alternative role set `{km, vmax, substrate_initial_concentration}` without an
  enzyme state (`RegistryRoleSet`, `RegistryProcessAssembler.role_set_for`);
  shipped cases assemble byte-identically. An optional `responses.csv` binds
  `temperature_cardinal_rosso`, `ph_cardinal_rosso` or
  `temperature_arrhenius_reference` to a strain, enzyme class and substrate
  through the case-template process modifiers, after checking the parameters,
  their dimensions, the law's own domain and that the kinetic constants are
  stated at the law's reference condition (exactly, within a stated
  `reference_tolerance`, or declared with `kinetics_at_reference`). Estimated
  law parameters make the whole law an exploratory prior. Gap requests name
  the rate form the user started, or both forms when none was
  (`docs/user-data.md`).

- Command-line virtual experiments (CLI-001): the `fungmod` console script
  (`fungal_model.cli:main`, also `python -m fungal_model`) with `run`,
  `preflight`, `check-data` and `list`. `fungmod run --fungus NAME
  --substrate NAME` with `--environment`/`--condition` names or a
  `--temperature-c`/`--ph`/`--oxygen` grid, optional `--user-data` and
  `--registry`, prints the preflight table (status, missing items and their
  suggested experiments), simulates through `VirtualExperiment.simulate`, writes
  the tables, manifest and Markdown report (`--report` adds the HTML report),
  and prints each case's final metrics and threshold times, the limitations
  count and the provenance and limitations table paths. `--mode` is required;
  exploratory mode requires `--samples` and `--seed`, scientific mode refuses
  them; `--output` must be new or empty. Exit codes: 0 success, 1 simulation
  failure, 2 usage or input error (user-data issues as `file:row:column:
  message`), 3 a case blocked by the preflight, with its measurement requests.
  `DegradationScreenResult.case_summary()` and `summary_metrics()` read the
  existing tables, and `fungal_model.api.result_tables.preflight_policy` (was
  private) gives the per-mode simulation policy (`docs/cli.md`).

- User-supplied enzyme and kinetics tables into virtual experiments
  (USERDATA-001): `load_user_dataset` reads a directory with
  `user_dataset.yml` and CSV tables of strains, enzyme classes, substrates,
  conditions and kinetics, collects every validation issue (file, row, column,
  message) into one `UserDataError`, and returns a `UserDataset` of
  `<dataset_id>__`-namespaced production registry mappings with a SHA-256
  digest. `VirtualExperiment.from_registry`, `from_names` and
  `virtual_experiment` take `user_data=` and overlay the records in memory
  before name resolution; the summary and output manifest record
  `user_dataset_id` and `user_dataset_digest`. Evidence types map to the
  maturities `user_measured`, `user_reported_literature`, `user_design_value`
  and `exploratory_prior`; missing roles become `user_dataset_gap` unknowns
  whose `measurement_request` provenance preflight now quotes as the suggested
  experiment. `fungmod_user_dataset` is a reserved provenance namespace.
  Homogeneous Michaelis-Menten on dissolved substrates only
  (`docs/user-data.md`).

- Axisymmetric grid geometry for the spatial mycelium core, colony observables
  (counts outside an inoculum disc, window-truncated hull radius and area) and the
  Rosso and Robinson cardinal water-activity law and modifier (SPATIAL-002);
  banded LSODA on one-axis grids and a coloured finite-difference sparse
  Jacobian for the implicit methods; the COLONY-001 stage 0 study module and
  runner (error models and recorded software checks, no fit).
- Frozen plan for the colony comparison (COLONY-001): the within-study
  transfer test of the continuum mycelium against the De Ligne 2019 curves,
  declared with its geometry, observation operators, error model, hold-outs,
  stages and decision rules before any software or fit, digest-pinned.
- De Ligne et al. 2019 colony growth dataset (DATA-003): hourly mycelial area
  and tip counts of *Coniophora puteana* and *Rhizoctonia solani* under sixteen
  temperature-humidity conditions, digitized from the supplementary figures by
  `scripts/digitize_de_ligne_2019_figures.py` with the source PDFs preserved
  under `data/experiments/source_intake/de_ligne_2019/`, both panel readings
  of every value stored with their difference, and every reading limitation
  flagged. `literature_processed`; no model comparison yet.
- `fungal_model.mycelium` (SPATIAL-001, exploratory): a continuum mycelium
  on a compiled finite-volume core in one to three dimensions. `SpatialGrid`,
  `FieldSpec`, the `FieldProcess` contract and ten generic processes (tip
  extension with an optional substrate-saturating speed and cost, tip motion
  by diffusion and drift, lateral and dichotomous branching, anastomosis,
  first-order losses, local uptake, translocation with an active term towards
  tips, local secretion, field diffusion), each with assumptions, validity
  labels, failure modes and literature-form provenance; `MyceliumModel.compile`
  resolves every unit once and refuses bad declarations; `MyceliumResult`
  reports integrals, occupied measure and front position. Verified against
  the pulled-front speed of the Edelstein system, conservation, symmetry,
  solver agreement and two unit systems (`docs/spatial-mycelium.md`). No
  organism parameters and no colony data yet.
- Gelain model-criticism study, amendment 4 (CRIT-004): the
  `M2_soluble_product_pool` all-condition posterior is re-recorded from the
  converged stage A fit with 36000 steps (still not converged; multiplier
  interval [1.63, 2.23], added constants bounded on one side or prior
  dominated, outcome unchanged and provisional), and the plan's holdout
  posteriors run per fold through `run_gelain_2020_model_criticism.py
  stage-b --hold-out` with the held-out loading scored by posterior
  predictive coverage (held-out coverage 22/32, 69 percent with 10 g/L held out, 32/32, 100 percent with 20 g/L held out, 19/32, 59 percent with 30 g/L held out, none of the three fold chains converged). `posterior_predictive_coverage`
  takes an explicit condition list; table 4 and the manifests regenerated.
  The PEtab cross-solver plan re-pins the amended criticism plan in a second
  dated amendment that keeps its recorded results valid.
- The software paper is a LaTeX manuscript, `paper/paper.tex` (it replaces
  the Markdown draft; `make paper-pdf` builds it with latexmk). The paper
  tables are now also written as LaTeX fragments (`paper/tables/*.tex`,
  captioned full-width floats generated next to the Markdown copies by the
  same command and checked the same way; `latex_inline` escapes cell text)
  and the figures also as PDF (`paper/figures/*.pdf`, generator marker, no
  date); the manifests name the new files and `check` covers them.
- The compiled process core assembles a Jacobian (`CompiledModel.jacobian`)
  from per-process gradient kernels: analytic through the new
  `Process.compile_jacobian` for `first_order_decay`, `mass_action`,
  `homogeneous_michaelis_menten`, `proportional_synthesis`, the three
  resource-limited closure processes and the two exchanges; central finite
  differences of the process's own rate kernel otherwise, with every kind
  recorded in the kernel summary (`jacobian_kernels`,
  `analytic_jacobian_count`). `SolverSettings(jacobian="compiled")` hands it
  to the implicit methods; the default (`finite_difference_by_backend`) and
  every recorded result are unchanged.
- The software paper's figures (`paper/figures/`): `fungal_model.research.paper_figures`
  draws the cellulose holdouts, the posterior predictive bands, the stage A
  screen and the cross-solver objectives from the recorded results, writes
  the plotted numbers as JSON next to each SVG and a manifest with source
  digests and key numbers; `scripts/reproduce_paper.py tables` and `check`
  (and `make paper-tables`, `paper-check`) now cover tables and figures.
- `fit_least_squares` accepts `diff_step`, `ftol`, `xtol` and `gtol`
  (each `None` by default, leaving scipy's value) and records the declared
  values in `optimizer_metadata`, so a calibration whose predictions come
  from an adaptive integrator can declare a finite-difference step above the
  integrator's step noise, as the model-criticism study does through its
  plan (CRIT-003). Default behaviour is unchanged.
- Culture physiology as generic processes on the compiled core
  (`fungal_model.processes.culture`): `resource_limited_growth`,
  `resource_limited_maintenance` and `costed_secretion` express the Pirt/Monod
  closure with explicit stoichiometry and optional extent ledgers;
  `dilution_exchange` and `gas_transfer` express the chemostat boundary with
  optional boundary ledgers; all five have numeric kernels, factories and
  config support (`stoichiometry` on `ProcessConfig`), and the packaged
  `toy_resource_limited_chemostat.yml` runs them on abstract pools.
  `ResourceLimitedCulture` and `DegradingCulture` gain `compiled_processes()`,
  `compiled_parameters()` and `simulate_compiled()`, which return the classes'
  own trajectory types from the compiled core; `simulate` keeps the native
  right-hand side (analytic piecewise Jacobian) and both paths name their
  engine in `diagnostics["engine"]`. Parity tests pin the two paths to 1e-6
  relative (`tests/test_culture_processes.py`). `FungalCouplingModel` gains
  `compiled_processes(degradation)`, `compiled_parameters()` (with the derived
  secretion-cost rate constant `alpha_E_c_E`) and `simulate_compiled()`, pinned
  to its legacy engine (`tests/test_coupling_compiled.py`); `MassActionProcess`
  accepts `catalysts` (species in the rate law that are not consumed; config key
  `states.catalysts`; SBML modifiers).
- Reproducibility package for the software paper
  (`docs/reproducing-the-paper.md`): `fungal_model.research.paper_tables`
  generates the paper's five tables under `paper/tables/` from the recorded
  study results with a manifest of source files, SHA-256 digests and key
  numbers; `scripts/reproduce_paper.py` offers the tiers `tables`, `check`,
  `verify` (digest chains, the compiled-core objective at the recorded
  cross-solver optimum, the stationarity of the recorded baseline fit),
  `stage-a` (re-run and compare) and `full` (every study, compared on
  verdict-level fields); `make paper-tables`, `paper-check`, `paper-verify`,
  `paper-stage-a`, `paper-full`, `wheelhouse` and `install-offline`; CI
  installs the built wheel with network access disabled from a wheelhouse of
  the pinned runtime closure.
- Gelain 2020 cross-solver reproduction (`docs/gelain-cross-solver.md`): the
  registry hydrolysis candidate exported as a three-condition PEtab problem and
  reproduced in COPASI under a frozen plan. COPASI's time courses agree with
  the compiled core to 1.7e-8 of sigma at FungMod's optimum; COPASI then finds
  an objective 1.3 percent lower, which FungMod evaluates to the same value, so
  the recorded stage A optimum is an optimiser stopping point, reported as
  such (`copasi_improves`).
- `fungal_model.standards.copasi`: import a FungMod PEtab problem with
  COPASI's PEtab importer (in a fresh interpreter), rewrite the column weights
  from sigma to `1/sigma^2`, tighten the integrator, simulate, fit locally and
  from seeded random starts, and re-evaluate every optimum on the PEtab
  objective. New optional extra `copasi`.
- `conditions_to_petab`: multi-condition PEtab export from assembled models
  with condition columns for species and parameters that differ between
  conditions and explicit noise scales per observable.
- SBML export of `proportional_synthesis`, of parameter-bound stoichiometric
  coefficients (`CoefficientBinding` on product maps, written as separate
  reactions so the parameter stays live) and of assay-activity units (named
  dimensionless unit definitions, listed in the model notes);
  `to_sbml(names_as_ids=True)`.
- Gelain 2020 model-criticism study (`docs/gelain-model-criticism.md`): a
  frozen, digest-pinned plan comparing an induction state, a soluble product
  pool with Monod uptake and product inhibition, and conversion-dependent
  accessibility against the registry hydrolysis candidate;
  `fungal_model.research.gelain_criticism` composes the variants from the
  registry base configuration, runs whole-condition least-squares holdouts
  with the v2 screen (stage A) and posterior sampling with identifiability
  and coverage (stage B); `scripts/run_gelain_2020_model_criticism.py`.
  Results are not yet recorded.
- Generic `substrate_reactivity` rate modifier
  (`fungal_model.modifiers.reactivity`): rate times `(S / S_ref)^n` after the
  Kadam 2004 substrate reactivity factor, with a compiled kernel and config
  builder; tested on a non-cellulose toy process.
- `posterior_predictive_coverage` in `fungal_model.calibration.bayesian`: the
  fraction of fitted observations inside the central posterior predictive
  interval with measurement noise.
- Bayesian calibration and identifiability (`docs/bayesian-calibration.md`):
  `fungal_model.calibration.bayesian` samples the posterior of a configured
  or registry case with the Goodman-Weare affine-invariant ensemble move over
  explicit `log_uniform`/`uniform` priors and explicit `GaussianObservationError`
  models, optionally with noise-scale multipliers (one per observable or one
  shared by a declared group) labelled `estimated_from_residuals`; reports
  integrated autocorrelation times,
  effective sample sizes and a declared convergence rule; classifies every
  parameter with declared thresholds (`identified`, `weakly_identified`,
  `bounded_above_only`, `bounded_below_only`, `prior_dominated`); computes a
  finite-difference Fisher information at the best sample and posterior
  predictive bands; and pools within-time replicate scatter into a
  measured-evidence error model. `fungal_model.calibration.compiled_predictor`
  evaluates configured conditions on the compiled core by rebuilding the
  config per candidate, and `fungal_model.screening.registry_case_config_factory`
  (with `resolve_registry_case` and `build_resolved_case_config`) rebuilds a
  registry case with exact value overrides so that template-derived
  coefficients follow the fitted symbol.
- Recorded posterior-sampling study of the *T. harzianum* P49P11 cellulose
  registry case (`data/benchmarks/gelain_2020_bayesian/`,
  `scripts/run_gelain_2020_bayesian_calibration.py`,
  `fungal_model.research.gelain_bayesian`): nine constants, three loadings,
  v2 bounds as log-uniform priors, assumed error model with one sampled shared
  scale multiplier, checkpointed parallel run, thinned posterior samples and
  identifiability verdicts recorded in the provenance of the nine calibrated
  registry records without changing their point values; a per-observable
  multiplier variant is recorded as an unconverged sensitivity study that
  diagnoses the biomass/cellulose misfit.
- Candidate review `pakula_2016_t_reesei_protein_load_review.yml` (status
  `proposed`, no values) for replicate-level cultivation data.
- Environment response laws (`docs/environment-response.md`): Rosso cardinal
  temperature (`temperature_cardinal_rosso`, CTMI) and cardinal pH
  (`ph_cardinal_rosso`, CPM) modifiers (`fungal_model.kinetics.cardinal`,
  `fungal_model.modifiers.cardinal`); a diprotic pH-ionization
  Michaelis-Menten process law (`ph_ionization_michaelis_menten`,
  `fungal_model.kinetics.ionization`, `fungal_model.processes.ionization`)
  matching the SABIO-RK pH-dependent law form; and a first-order Arrhenius
  thermal-inactivation process law (`thermal_inactivation`,
  `fungal_model.kinetics.inactivation`, `fungal_model.processes.inactivation`).
  All compile to numeric kernels, validate their parameters, require sources,
  and warn outside declared measured ranges. Factories, config builders,
  configured-output rows and two non-biological toy configs are included.
- Registry templates bind the new modifiers through role fields and the new
  process laws through their `process_type`; the environment entity is
  generated for every condition a bound law reads. Assembled configs record
  `provenance.environment_response`; `RegistryCaseEnsemble` carries it and
  the virtual-experiment tables derive `environment_effect_status:
  active_response_model` from it, list the laws in
  `environment_response_model`, and allow environment ranking only when every
  condition that varies across the screen is covered by a law or
  condition-specific records.
- First registry case with an active response law: *Phanerochaete
  chrysosporium* K-3 BGL1A on cellobiose over pH 4 to 8 (SABIO-RK Reaction 618
  entry 38522, Tsukada et al. 2008). Fungus, five environment, compatibility
  and template records, eight `literature_processed` constants copied verbatim
  from the archived raw export (SHA-256 recorded) and two explicit
  `exploratory_prior` loading assumptions; exploratory mode only.
- Candidate review for *T. harzianum* cardinal temperatures
  (`data/experiments/candidate_reviews/trichoderma_harzianum_cardinal_growth_review.yml`),
  proposed with no transcribed values.

- First whole-organism registry case: *Trichoderma harzianum* P49P11 on
  Celufloc 200 cellulose (Gelain 2020) runs in `scientific` mode through
  `VirtualExperiment` with biomass, filter-paper and beta-glucosidase activity,
  cellulose and two closure-ledger trajectories. Fungus, enzyme-class,
  substrate, three culture-condition, compatibility and template records plus
  nine `calibrated` parameter records (artifact path, SHA-256, training
  conditions, rank diagnostics and at-bound flags) and four deposited initial
  conditions (`docs/organism-physiology.md`).
- `culture_physiology` case-template family
  (`fungal_model.screening.culture_physiology`): generic multi-process
  assembly with `biomass` and indexed `ledger_*` state roles, product-map
  coefficients bound to parameter roles (`parameter_role`,
  `complement_of_parameter_role`), a build-time closure check and fail-closed
  role accounting; registered as a `scientific`/`toy` assembler.
- `proportional_synthesis` process (`ProportionalSynthesisProcess`,
  `ProportionalSynthesisFactory`): producer-proportional formation of a
  product pool with optional saturable induction, compiled to a numeric
  kernel, with a non-biological toy config
  (`data/model_configs/toy_proportional_synthesis_dissolved.yml`).
- Assay-activity base units in the core registry: `filter_paper_unit` (`FPU`)
  and `beta_glucosidase_assay_unit` (`BGU`); the Gelain research units
  `gelain_fpu`/`gelain_beta_u` are now aliases of them.
- Compiled well-mixed model core (`fungal_model.solvers.compile_assembled_model`):
  units resolve once at build time, stoichiometry is probed from
  `Process.contributions` and checked for linearity, and every shipped process
  and modifier supplies a numeric rate kernel. Dynamic Gibbs constraints compile
  to a float feasibility test. `solver_metadata["kernel"]` records each
  process's kernel kind; processes without a kernel use an explicit, exact
  unit-aware fallback. Trajectories and evaluation counts are unchanged on every
  packaged config; solves are 6 to 60 times faster.

- Opt-in balanced secretion–digestion–growth feedback with seven dynamic pools,
  explicit protein synthesis costs, chemically retained inactive protein,
  substrate allocation and batch degradation thresholds. Illustrative kinetics
  remain separate from measured total-protein output.
- Checksummed Jørgensen 2009 primary data, entire-strain protein-output holdouts,
  an offline coupled-culture runner and four plots, including a kinetic
  sensitivity envelope. No whole-fungus validation or registry promotion.
- Opt-in conserved growth/maintenance respiration with nitrogen/oxygen limitation,
  gas transfer, batch/chemostat dynamics, open material balances and explicit
  unmet-maintenance diagnostics. Complete sourced energies are required for entropy.
- Two checksummed A. niger primary datasets, training-only Pirt holdouts,
  external-regime challenges, error-corner sensitivity and four reproducible plots.
  Inconsistent source cells remain quarantined; whole-fungus validation is open.

- Unit-bearing per-state solver tolerances and first-step control across main
  engines; sparse Cartesian Jacobians for supported local spatial dynamics.
- Sourced closed detailed-balance reaction networks with analytic Jacobians,
  independent free-energy equilibrium, conservation and entropy diagnostics.
- Reproducible four-solver replay of 33 existing culture holdouts and plots;
  explicit refinement resolves a BDF depletion failure without clipping.
- Conservation-law macrochemical balance in `fungal_model.chemistry`: solves
  overall exchange stoichiometry from element and charge conservation and forms
  reaction energies and an entropy budget from sourced formation energies. A
  constraint layer only; it predicts no rate or yield.
- Joint Gelain culture/activity benchmark with published-equation refits,
  activity-driven hydrolysis and retained dry-mass alternatives, 33 condition
  holdouts, explicit covariance sensitivity, profile loss and conditional
  bootstrap. FPU and pNPG activity remain separate assay dimensions.
- Generic sourced Gaussian covariance and single-response censoring, plus
  frozen model/observation/scope/criteria contracts for independent validation.
  Current culture models retain explicit missing-evidence status.

- Added the bounded Gelain 2020 T. harzianum culture benchmark: unit-aware source
  reproduction, an explicitly exploratory growth/loss model, six whole-condition
  holdouts, weighting sensitivity, frozen artifacts and cross-solver checks.
  Missing replicate uncertainty and substantial cellulose prediction errors
  remain explicit; no validated organism model or registry promotion is claimed.

### Changed

- Text only (FETCH-002): `fungmod assemble --help` describes `--fetch` as the
  opt-in for the UniProt proteome and the kinetics lookup, and `--cache-dir`
  as where kinetics snapshots are read and stored; `--fetch` without a
  proteome option and without `--fetch-kinetics` is still refused, with a
  message that names both. No numerical behaviour changes.

- Text only (ASSEMBLE-002): the refusal of a network dataset as `user_data` of
  `assemble_user_tables` now names `network=True` (`fungmod assemble
  --network`), which accepts it. No numerical behaviour changes.

- Text only (FETCH-001): `UniprotSnapshot.genomes_row` (and so
  `write_snapshot_to_user_dataset`) prefixes its `source` with the export's
  organism and taxonomy id; an assembled draft's manifest `source` and
  `review.md` call a UniProt export "UniProt proteome export" instead of
  "dbCAN annotation" (also for a UniProt row reused from `user_data`), list
  its unresolved EC numbers and EC/CAZy disagreements, and count proteins
  rather than genes for its classes (which previously raised a `KeyError` in
  `review.md` for an unmodellable class of a reused UniProt row); the draft's
  limitations name UniProt exports among the offline sources. The command
  line's no-fetch sentence (`NO_FETCH_HELP`) now names `assemble --fetch` as
  its one network opt-in. No numerical behaviour changes.

- The `culture_physiology` assembler accepts `rate_units_from_state_role` on a
  process template (the rate in the units of that state's initial record per
  unit of the time grid; refused together with a fixed `rate_units` or with an
  undeclared state role) and an explicit `geometry: null` (a concentration-only
  model without a geometry entity; a missing or empty geometry is still
  refused) (USERDATA-009). The output tables state the retrospective-calibration
  limitation of a culture case only when it binds a `calibrated` record, and
  "Enzyme pools are assay activities" only when every pool record is in assay
  units; the shipped *T. harzianum* case's configs and output tables are
  byte-identical.

- User-dataset gap requests name the measured condition (ASSEMBLE-001): when
  a strain, enzyme class and substrate have kinetic constants at other
  conditions of `conditions.csv` but none at this one, each gap's measurement
  request adds "kinetics.csv states kinetic constants of this strain, enzyme
  class and substrate only at <condition> (<temperature>, <pH>), and FungMod
  does not reuse kinetics measured at another condition". Values, records and
  gaps are unchanged. The loader's categorical compatibility rule is exposed as
  `fungal_model.api.user_data.enzyme_class_acts_on` and used by the assembly.

- README and documentation accuracy audit (DOCS-001): the README's current
  limitations now describe the implemented temperature and pH laws, thermal
  inactivation, posterior sampling, the compiled culture closures, the
  exploratory spatial mycelium and the runnable organism records; the
  cross-solver summary reports the recorded `reproduced` outcome; the source
  proposal example selects entry 35622 so the review step runs; the capability
  map, compiled-core, colony, quickstart, user-guide, standards, install and
  paper pages were corrected against the code. Documentation only.
- Gelain model-criticism stage A (`fungal_model.research.gelain_criticism`):
  the least-squares optimiser reads its finite-difference step, tolerances
  and restart rule from the plan's new `stage_A_least_squares.optimiser`
  block (`OptimiserSettings`, no defaults), records them with every fit, and
  restarts the best start from its own solution until the relative cost
  decrease is below the declared tolerance. Plan amendment 3 (digest
  `9897ab11...`) declares a log-space difference step of 1e-3, tolerances of
  1e-10 and up to three restarts; stage A was re-run for every model under
  it. `refresh_stage_b_verdicts` and the `refresh-verdicts` subcommand
  recompute a recorded posterior's R1 component against the stage A
  comparison on disk and re-digest the two files they rewrite.
- Gelain cross-solver reproduction re-run against the new reference fit under
  a dated amendment of its plan (digest `cfb8c9a6...`): outcome `reproduced`
  (COPASI's local fit within 2.5e-8 of FungMod's optimum, every parameter
  within 1e-4 relative, no random start lower).
- `EnvironmentGrid` runtime cases and the virtual-experiment registry overlay
  no longer assert that temperature and pH are inert; their status is the
  status before assembly and the assembled case decides. Metadata-only
  behaviour is unchanged for cases that bind no law.
- The runtime-grid overlay no longer copies condition-specific records that
  differ only by registry environment (the three Gelain cellulose loadings):
  a grid over *T. harzianum* reports the loading as missing and lists the
  symbol under `ambiguous_condition_specific_symbols` instead of silently
  taking one condition's value.
- `beta_glucosidase` enzyme class lists `ph_ionization_michaelis_menten` as a
  compatible process; the SABIO-RK rice-enzyme case still selects plain
  Michaelis-Menten.

- Compiled models evaluate every rate at `max(state, 0)` (recorded as
  `negative_state_policy` in `solver_metadata["kernel"]`) so that a pool can be
  consumed to depletion without the solver's trial iterates raising; the
  integrated trajectory is never clipped and the `non_negative` validator still
  reports accepted states below tolerance. Process rates recorded at output
  points use the same projection. The unit-aware `Process.rate` API stays
  strict for caller-supplied negative states.
- Modelability no longer marks a case underparameterized because an organism
  carries an enzyme class that does not target the requested substrate; such
  classes are reported as known, unused items when another class reaches a
  compatible process. Registry compatibility selection skips enzyme classes
  without a compatibility record instead of raising.
- `ProcessODESolver` integrates the compiled right-hand side. Environment-only
  rate modifiers are evaluated once per run, so their source-range warnings fire
  once rather than at every right-hand-side evaluation. `_record_process_rates`
  reuses compiled kernels for unconstrained processes.

### Fixed

- A dimensionless parameter bound to a product-map coefficient in scaled units
  was read as its raw number: a `culture.csv` `biomass_yield` of `0.5 mg/g`
  acted as 0.5 g/g, a thousand times too large, and `350 mg/g` or `35 percent`
  were refused as above 1 g/g. The composition builder now converts such a
  record to a plain fraction with pint, and the culture bound is judged in
  g/g. Records in `g/g` or `dimensionless`, every registry case and every
  fixture are unchanged (their configs hash as before).

- `final_metrics.csv` named a product stated in micromolar
  `final_product_amount` (and would have called an amount per mass such as
  `millimole / gram` a concentration): the label was chosen by matching unit
  names as text. It is now chosen by pint's dimensionality: anything per volume
  is `final_product_concentration`, anything else `final_product_amount`.
  Output schema `2.2.1` (was `2.2.0`): no table, column or allowed value
  changed, but bundles of earlier versions carry `final_product_amount` for
  micromolar products (the esterase, oxidase and parallel-network fixtures,
  for example), so do not pool the two names across versions; every other
  label and every value is unchanged (NETWORK-002).
- The homogeneous and pH-ionization Michaelis-Menten assembler labelled every
  substrate entity dissolved (`generic_dissolved` loader, `physical_state`
  `dissolved`, `homogeneous_dissolved` degradation model) whatever the
  registry substrate declared (USERDATA-008). It now reads the substrate
  record's physical state: a dissolved substrate keeps exactly those labels (the
  shipped and user dissolved configs are byte-identical), any other substrate
  gets the generic solid loader, its own physical state and an `unknown`
  default degradation model. The case-template modifier binding also accepts
  the existing `substrate_reactivity` modifier (substrate state role,
  reference-concentration role and exponent role, none defaulted).

- A case could be preflighted on one enzyme class and built from another
  (FIX-SELECT-001). When a fungus listed several enzyme classes acting on one
  substrate (common once genome annotations or proteomes add classes to a user
  strain), `assess_modelability` evaluated every compatible process record and
  selected one, but kept only its process type; `select_registry_case_compatibility`
  then took the first compatible record in the fungus's listing order. A case
  reported modelable on the complete parameters of class B was assembled from
  class A, listed first: an assembly error after a passing preflight, or a
  simulation of an enzyme the preflight did not assess. `ModelabilityReport`
  now records `selected_compatibility_id` and `selected_enzyme_class` (also in
  `to_dict()`, so in `virtual_experiment_summary.json` and
  `screen_summary.json`); config assembly, the exploratory and scientific
  screens and the result tables build the case from exactly that record,
  checked against the case, and the tables resolve it once per case and refuse
  a preflight report that selected a different record. A report built without
  the new fields is resolved only when the case has one candidate record, and
  refused with the candidates named otherwise. Every shipped case has one
  candidate: selection, assembled configs and the standard CSV tables are
  unchanged, and the output schema stays `2.0.0`.

- Degradation and product-release rates in the virtual-experiment tables were
  wrong (FIX-RATES-001). `time_series_long.csv` built `degradation_rate` and
  `product_release_rate` from whichever process rate was listed last at each
  time point and gave both rows that one value and unit; `final_metrics.csv`
  reported `maximum_substrate_depletion_rate` and
  `maximum_product_release_rate` as the largest rate of any process, whatever
  its process or unit. For models with more than one process the reported
  rates therefore belonged to an arbitrary process: the *T. harzianum* P49P11
  culture case reported a maximum substrate depletion rate of about 45
  `beta_glucosidase_assay_unit / hour / liter` for cellulose measured in g/L.
  For single-process cases with a product yield other than one the product
  release rate was the process rate, not d[product]/dt: the SABIO-RK Reaction
  618 case (two glucose per cellobiose) reported half the true value. All
  previously reported maximum rates and product-release rates from such cases
  are wrong. `ProcessODESolver` now records `SimulationResult.state_rates`, the
  net rate of change of every state at every returned time point, by
  evaluating the compiled right-hand side it integrated (rates at
  `max(state, 0)`, no finite differences), written to `state_rates.csv` and
  `record.json`. The tables take `degradation_rate` = -d[substrate]/dt and
  `product_release_rate` = +d[product]/dt from it, each in its own state's
  units per time (source `simulation_state_rate`), and the maximum-rate
  metrics are their maxima over the returned time points. A case without a
  mapped substrate or product state, or a bundle without `state_rates.csv`,
  reports these rows and metrics as `not_applicable` with the reason in a new
  optional `notes` column of `time_series_long.csv` (and in `final_metrics.csv`
  `notes`); process rates are never used in their place, and the
  `process_rate.<process_id>` rows are unchanged. Output schema `2.0.0`
  (was `1.8.0`): rows keep their names but change meaning, values, units and
  source, so do not pool `1.8.0` and `2.0.0` bundles; regenerate earlier
  virtual-experiment outputs that use these rates. No committed data or paper
  artifact contains them.

- SABIO-RK proposals gave every parameter of one type the same proposed symbol
  when its species did not distinguish them, so the four pKa values of a
  pH-dependent kinetic law collided (`proposed_sabiork_parameter_618_38522_pka`)
  and the whole Reaction 618 proposal could not be reviewed. The SABIO-RK
  parameter name now completes such symbols (`pka_pke1`, `pka_pkes2`); symbols
  whose name adds nothing are unchanged (FIX-DOCS001).
- Preflight reported the pH-ionization Michaelis-Menten case as modelable in an
  environment whose pH is a range, after which every simulation sample failed.
  Preflight now checks the environment conditions each process law reads
  (`PROCESS_ENVIRONMENT_CONDITIONS`: pH for the ionization law, temperature for
  thermal inactivation) and reports a range or unknown as blocking, with the
  remedy (FIX-DOCS001).
- Importing the COPASI stack through `fungal_model.standards.copasi` no longer
  leaves the process in the C locale. COPASI's static initialiser calls
  `setlocale(LC_ALL, "C")`, which switched Python's preferred text encoding to
  ASCII, so every later text read that named no encoding failed on non-ASCII
  repository files once the `copasi` extra was installed (the culture-benchmark
  docs check in CI). The import helper restores `LC_CTYPE` and keeps COPASI's
  numeric locale; the COPASI test modules skip through that helper instead of
  importing COPASI directly; a regression test checks the encoding in a fresh
  interpreter. The FungMod-objective check of the cross-solver test tolerates
  platform floating-point differences (relative 1e-7; macOS differed from
  Linux by 1e-8).
- The cross-engine reference simulator compiles kinetic laws from their L3
  infix text instead of libSBML `ASTNode` objects, so SBML round-trip and
  trajectory checks no longer fail once `libsedml` has been imported in the
  same process (SWIG proxy registry clash). Unsupported constructs still raise
  `SbmlExportError`, now at compile time.
- Repository data and documentation are read as UTF-8 explicitly; Windows
  no longer decodes `±` and non-ASCII text with cp1252. Frozen-artifact
  manifest paths compare as POSIX on every platform.
- The Gelain joint holdout replay test propagates the prediction tolerance
  into its score comparison instead of using a fixed 1e-6 absolute tolerance
  that activity predictions of order 1e3 U/L could not meet under current
  SciPy. Frozen artifacts are unchanged.
- Analytic piecewise Jacobians for resource-limited and integrated cultures
  prevent finite-difference perturbation overflow in non-feedback ledger states
  during depletion. Rate laws and conservation equations are unchanged.
- Incomplete/nonfinite main-engine integrations now raise `IntegrationError`
  instead of returning partial trajectories. Invalid numerical controls reject.
- Reversible net flux uses `expm1` to avoid cancellation near equilibrium.
- Fixed mixed-unit SBML trajectories, preserved PEtab training/validation/holdout separation, and rejected missing or zero export noise scales. Regenerate older affected exports.
- Fixed thermodynamic scalar typing and pinned the checked Pyright version for local/CI parity.
- Consolidated exploratory inhibition runners through shared unit-aware package integration and the configured inhibition kernel (FD-008 resolved).
- Added explicit-noise grid profile likelihood and checksum-bound frozen-prediction evaluation with raw replicate evidence. Independent empirical validation remains pending on suitable external data.
- Corrected configured calibration when uncertainty units differ from observation units.

- Removed the pNPG Michaelis constant from the cellobiose cross-source fit;
  the unknown cellobiose constant is estimated with explicit limitations.
- Comparison statistics now require an explicit fitted-parameter count for
  reduced chi-square and omit undefined values. Configured calibration records
  the training count and preserves pointwise uncertainties instead of averaging.
  Partial uncertainty fails explicitly; entirely unknown scales remain unweighted.
- Research runners check solver/optimizer success and nested-model consistency,
  verify reference trajectories against the configured package path, and report
  descriptive results instead of automatic mechanism conclusions. Research
  summary schemas are now `2.0.0`; regenerate historical study outputs.
- Added warnings for approximate confidence intervals outside optimizer bounds,
  reconciled literature-calibration guidance, and extended quality gates to
  research runners. No new empirical validation or biological mechanism is claimed.

### Added

- `fungal_model.chemistry.haldane`: Haldane relations tying reversible
  Michaelis-Menten parameters to the equilibrium constant, with
  `equilibrium_constant_from_gibbs`, `reverse_vmax_from_haldane`, and
  `check_haldane_consistency`. Given a sourced standard Gibbs energy and three
  measured parameters the fourth is determined rather than fitted, which removes
  a degree of freedom exactly where kinetic data is scarce. Scoped to uni-uni
  mechanisms; multi-substrate reactions are rejected, not approximated.
- `fungal_model.fungi.energetics.GibbsEnergyYieldBound`: a thermodynamic ceiling
  on biomass yield, `Y_max = |dG_catabolic| / dG_anabolic`. Wired into
  `FungalCouplingModel` as an opt-in `yield_bound`, so a configured yield that
  would create free energy is rejected before the model can run. Both Gibbs
  energies must be sourced; the bound invents no energy value.
- `fungal_model.capability`: genome-derived enzymatic capability resolution.
  A curated, literature-sourced CAZy family to enzyme-class map
  (`data_registry/cazyme_families/cazyme_family_map.yml`, 18 families), an
  offline dbCAN `overview.txt` parser, and a resolver that separates capabilities
  FungMod can model from capabilities the organism has but FungMod cannot, and
  family-diagnostic assignments from family-polyspecific ones. Presence and
  absence only: a test asserts the output carries no rate or kinetic constant.

- Two further literature sources, taking the repository to three independent
  sources, seven series, and four enzyme preparations across three kinetic
  regimes. `scripts/digitize_ariaeenejad_2020_figure_6.py` adds a 17-point,
  380 h PersiBGL1 series (Ariaeenejad 2020, CC BY);
  `scripts/digitize_cao_2015_figure_5a.py` adds two 6-point, 10 h series for
  wild-type Bgl6 and mutant M3 at 10 % w/v cellobiose (Cao 2015, CC BY 4.0).
  Both digitizers verify their axis calibration against values each source
  states in prose, independently of the figure, and refuse to write otherwise.
- `scripts/run_cross_source_structural_test.py`, which fits the shared rate-law
  structure to five selected series with and without enzyme deactivation, and
  reports numerical diagnostics for both fits without asserting identifiability.
- The Ariaeenejad 2020 candidate review moves from blocked to
  `approved_for_ingestion`, with a `resolution_review` block recording that the
  time-axis conflict was resolved by the figure's own x-axis label. The original
  blocked verdict is retained as the audit trail and marked superseded.

### Findings

- The stage A optimiser of the model-criticism study had been stopping above
  the minimum: with scipy's default finite-difference step (about 1.5e-8) the
  Jacobian differentiated the adaptive ODE integrator's step noise, derivative
  norms for weakly entering constants were fifteen times their converged
  values, and the trust region collapsed with every start reporting a
  satisfied step tolerance. The cross-solver reproduction found it (COPASI 1.3
  percent below FungMod's optimum); tightening the tolerances alone changed
  nothing; a declared log-space step of 1e-3 (the v2 plan already had one)
  brings every start of the baseline to the same minimum (objective 3.97607,
  projected gradient norm 2.5e-3 in log space against 0.22 before). The
  recorded stage A results and the cross-solver result were replaced under
  dated amendments; the stage B chains were not re-run (their initial centre is
  a starting point and they are reported as unconverged), and their R1
  components were refreshed against the new screen. Under the declared step
  the soluble product pool (M2) passes the R1 holdout screen in both
  scenarios with every observable better (pooled held-out error 23 and 26
  percent below the baseline); the first run had recorded it as failing
  because biomass worsened by 31 percent, which was the stalled optimiser.
  M2's outcome is now "improves fit but unidentified (R1, not R3)"; M1 and
  M3 still fail R1. The public `fit_least_squares` API still uses scipy's
  default step (follow-up).
- Earlier cross-source structural-adequacy and deactivation-warranted claims
  are superseded by the research-analysis corrections above. Training residuals
  and local Jacobian diagnostics do not establish those conclusions. The
  PersiBGL1 fit previously used a Michaelis constant from a different substrate;
  regenerate results with the corrected exploratory parameterization.
- Resa and Buckin (2011) is confirmed paywalled with no extractable observations
  and remains blocked.

- Three additional digitized series from Alvarez-Gonzalez et al. (2022)
  Supplementary Figure S1, taking the repository from nine to thirty-six real
  literature observations across all four series of that figure
  (`scripts/digitize_alvarez_gonzalez_2022_figure_s1.py`). The script verifies
  the supplementary PDF SHA-256 and refuses to write unless it first reproduces
  the previously committed Figure S1A filled-square series within the declared
  0.6 mM digitization resolution (achieved: 0.273 mM).
- A held-out condition study (`scripts/run_alvarez_gonzalez_2022_holdout_prediction.py`)
  predicting the three previously undigitized series from the publication's own
  Model 3 parameters with no FungMod fit.
- A two-stage calibration study
  (`scripts/run_alvarez_gonzalez_2022_stage2_calibration.py`) fitting FungMod
  parameters on one series and predicting the held-out conditions.
- Configured calibration now accepts `literature_raw` and `literature_processed`
  datasets in addition to `synthetic`, through an explicit
  `CALIBRATABLE_DATASET_MATURITIES` allowlist. Toy, framework, calibrated, and
  validated maturities still fail closed. A literature calibration records
  `dataset_maturity` and carries parameter-estimation assumptions and a
  non-validation warning instead of the synthetic-fixture wording.
- Within-source prediction residuals differ across substrate and nominal enzyme
  loadings. They do not establish general parameter transferability or uniquely
  attribute discrepancies to mechanism structure.
- A model-free comparison of the two panels gives an apparent enzyme scaling of
  `[E]^0.28`, against the `V_max = k_cat * [E]` linearity the configured model
  assumes. Recorded as an unsupported capability rather than tuned away.
- The Figure S1 caption's panel-B unit (`296.1 mg/mL` against panel A's
  `59.2 mg/L`) is refuted as printed by the data: it implies exhaustion of the
  222 mM charge in about 0.19 s against 36.66 mM observed at 60 min. The mg/L
  reading is adopted as an explicitly recorded assumption; the printed value and
  unit are preserved verbatim in the dataset records.
- In the four-parameter fit, the approximate interval for positive `K_i` extends
  outside its admissible range. This flags an unsuitable local interval or weak
  identification, not a negative physical constant. Fixing it at the source's
  point estimate is a conditional model choice, not new measurement evidence.

- SBML Level 3 export for the supported well-mixed kinetic processes
  (first-order decay, mass action, and homogeneous Michaelis-Menten) via the
  optional `standards` extra (`fungmod.standards.to_sbml`,
  `model_config_to_sbml`, `write_sbml`).
- Cross-engine trajectory checks: an independent reference SBML integrator and
  `cross_engine_trajectory_check`, confirming exported SBML reproduces FungMod's
  own solver trajectories to solver tolerance.
- SED-ML Level 1 Version 4 simulation export (`fungmod.standards.to_sedml`) and
  COMBINE archive (`.omex`) generation (`write_combine_archive`,
  `model_config_to_combine_archive`) bundling the SBML model with its SED-ML
  time course into one portable, byte-reproducible file.
- PEtab export for calibration cases (`fungmod.standards.calibration_config_to_petab`):
  writes a complete PEtab problem (SBML model, observable/measurement/condition/
  parameter tables, and `problem.yaml`) from a calibration config, with
  measurement values and times converted to the model's units. The result passes
  `petab.lint_problem`.
- SBO terms (added automatically by kinetic role) and MIRIAM annotation support
  (`MiriamAnnotation`, `to_sbml(annotations=...)`) in the SBML export.
- A BioModels-ready deposit for the SABIO-RK Reaction 618 β-glucosidase case
  (`fungmod.standards.write_biomodels_deposit`): annotated SBML (ChEBI, EC,
  UniProt, KEGG, MetaNetX, NCBI Taxonomy, PubMed), a COMBINE archive, and a
  submission README. Curated Km/kcat; initial concentrations are explicit
  assumptions.

### Fixed

- `fungmod.<subpackage>` nested imports (e.g. `fungmod.core.units`) now resolve
  to the exact same module object as `fungal_model.<subpackage>`, so shared
  state such as the pint unit registry is not duplicated across a registry
  boundary.

### Scientific scope

- SBML export refuses (rather than silently approximates) models with
  unsupported processes, rate-modifier wrappers, or dynamic thermodynamic
  constraints, so an exported model always matches FungMod's behaviour.

## [0.1.1] — 2026-08-01

### Added

- Packaged, provenance-labelled parameter input for five purified fungal
  beta-glucosidases reported on cellobiose at matched assay conditions.
- A deterministic full notebook with configured dynamic glucose inhibition,
  2:1 glucose stoichiometry, inhibition-free counterfactuals, scenario
  summaries, figures, validators, diagnostics, and manifests.
- One provenance-matched, no-refit comparison with nine digitized literature
  time-course observations.
- A generic coupled hydrolysis/substrate-transglycosylation process and one
  provenance-backed *Phanerochaete chrysosporium* BGL1B configuration.
- A minimal exploratory well-mixed fungal-process coupling API.
- Uniform Cartesian 2D/3D finite-volume reaction diffusion.
- Constant-activity-coefficient nonideal reversible thermodynamics with local
  detailed balance.
- Independent-input variance-based global sensitivity with Saltelli
  first-order and Jansen total-order estimators.
- A publication-oriented calibration evidence audit whose software pass never
  authorizes a publication claim.

### Changed

- Removed the tracked package-resource mirror. Source distributions now stage
  canonical `data/` and `data_registry/` bytes deterministically into wheels.

### Scientific scope

- The new cases model purified enzymes labelled by fungal source, not
  whole-fungus physiology.
- Literature parameters remain separate from the explicit 10 nM showcase dose
  and starting-concentration assumptions.
- The time-course comparison uses source-model parameters and observations
  from the same publication without refitting; it is not independent
  validation, and digitization resolution is not experimental uncertainty.
- The fungal coupling remains an artificial software-tested composition, not
  organism-specific physiology or whole-organism validation.
- Transglycosylation product identity/re-hydrolysis, empirical parameter
  distributions, correlated-input sensitivity, publication-grade biological
  calibration, model discrepancy, and organism ranking remain unavailable.

## [0.1.0] — 2026-07-30

### Added

- PyPI distribution name `fungmod` with Python 3.11–3.13 metadata.
- `fungmod` convenience import namespace while retaining `fungal_model`.
- Immutable wheel-packaged registry, frozen source evidence, and example data.
- Public `default_registry_path()`, `example_data_path()`, and
  `package_data_path()` helpers.
- Installed-wheel fallback for the default virtual-experiment registry,
  frozen SABIO-RK Reaction 618 source proposal, configured example paths, and
  PET plugin benchmark assets.
- Artificial, framework-labelled dynamic-thermodynamics showcase configuration.
- Full zero-to-report and advanced-capabilities notebooks.
- MkDocs Material documentation configured for Read the Docs.
- Deterministic notebook/resource drift checks and isolated-wheel smoke tests.
- Trusted Publishing release workflow and expanded CI release gates.

### Scientific scope

- No new organism-specific biology or empirical validation data were added.
- The advanced inhibition and thermodynamic examples are artificial software
  benchmarks with explicit provenance, maturity, assumptions, and limitations.
- Existing exploratory ranges remain exploratory; they were not reclassified
  as calibration or validation evidence.

[Unreleased]: https://github.com/felixlaga/FungMod/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/felixlaga/FungMod/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/felixlaga/FungMod/releases/tag/v0.1.0
