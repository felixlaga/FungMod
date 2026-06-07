# DATA-002 Reaction 618 Parameter Ranges

Date: 2026-06-07

Status: complete for local SABIO-RK Reaction 618 multi-entry curation.

## Scope

DATA-002 hardened the existing local SABIO-RK Reaction 618 snapshot into
provenance-rich parameter-range artifacts for the beta-glucosidase/cellobiose
homogeneous Michaelis-Menten case.

No live SABIO-RK API request was used. No new reactions, substrates, or
biological mechanisms were added.

## Raw Snapshot

The curation used:

- `data/kinetic_records/sabiork/case_001_reaction_618_beta_glucosidase/raw/kinlaw_entries_reaction_618.json`

The source snapshot contains 29 kinetic-law entries for SABIO-RK Reaction 618.

## Inclusion And Exclusion

Entries were included only when they matched all scoped DATA-002 criteria:

- SABIO-RK Reaction ID 618;
- reaction involving Cellobiose and beta-D-Glucose;
- beta-glucosidase enzyme with EC 3.2.1.21;
- plain Michaelis-Menten kinetic law;
- explicit Km for Cellobiose with mM units;
- explicit kcat with s^(-1) units.

Every excluded entry is written to
`reaction_618_excluded_entries.csv` with an explicit reason. The current local
snapshot yields:

- included entries: 15;
- excluded entries: 14.

## Curated Outputs

DATA-002 creates or updates:

- `data/kinetic_records/sabiork/case_001_reaction_618_beta_glucosidase/curated/reaction_618_eligible_entries.csv`
- `data/kinetic_records/sabiork/case_001_reaction_618_beta_glucosidase/curated/reaction_618_excluded_entries.csv`
- `data/kinetic_records/sabiork/case_001_reaction_618_beta_glucosidase/curated/parameter_range_summary.json`
- `data/kinetic_records/sabiork/case_001_reaction_618_beta_glucosidase/curated/parameter_range_summary.md`

The eligible-entry table preserves EntryID, organism, enzyme name, EC number,
enzyme type, kinetic-law type, Km/kcat values and units, pH, temperature,
buffer, publication metadata, PubMed ID, and source JSON fields.

## Parameter Ranges

The all-eligible literature ranges from the local snapshot are:

| Parameter | Count | Lower | Upper | Units |
| --- | ---: | ---: | ---: | --- |
| Km_cellobiose | 15 | 0.68 | 114.0 | mM |
| kcat_cellobiose | 15 | 0.13 | 7.17 | s^(-1) |

The report also computes scoped ranges for:

- all_eligible;
- by_organism;
- by_pH_exact;
- by_temperature_exact;
- by_organism_and_pH;
- wildtype_only;
- mutant_only.

Each parameter range includes count, lower, upper, min/max EntryID, median,
mean, p05, p50, p95, units, EntryIDs, and a status. Groups with fewer than two
entries are retained and marked `insufficient_n`.

## Scientific Interpretation

The Km/kcat ranges pool multiple SABIO-RK Reaction 618 entries across organisms
and/or assay conditions. They are useful as exploratory literature priors, not
as selected-entry uncertainty or calibrated pH/temperature response laws.

These ranges do not overwrite the selected exact EntryID 35622 values. They do
not replace the unknown enzyme concentration record, and they do not change the
explicitly exploratory enzyme concentration prior.

## Virtual-Experiment Use

The registry keeps the broad all-eligible Km and kcat ranges as
`literature_range` records with curation-file provenance. The virtual-experiment
sampled-parameter table now reports a `parameter_source_class` so downstream
tables can distinguish:

- selected exact value;
- literature range;
- user-supplied exploratory prior;
- unknown.

Scientific-mode preflight still does not silently use the broad literature
ranges as exact values.

## Remaining Data Debt

- The local snapshot is a fixed SABIO-RK export and may not reflect future
  database changes.
- No unit conversion is performed.
- pH and temperature are preserved as metadata, not modeled as response curves.
- Broad cross-entry ranges are not posterior uncertainty estimates.
- Whole-fungus growth, secretion, transport, biomass, and respiration remain out
  of scope for this Reaction 618 enzyme-source case.
