# SABIO-RK Reaction 618 Parameter Range Summary

## Scope

- Source export: `data/kinetic_records/sabiork/case_001_reaction_618_beta_glucosidase/raw/kinlaw_entries_reaction_618.json`
- Source reaction ID: `618`
- Included entries: 15
- Excluded entries: 14

The Km/kcat ranges pool multiple SABIO-RK Reaction 618 entries across organisms and/or assay conditions. They are useful as exploratory literature priors, not as selected-entry uncertainty or calibrated pH/temperature response laws.

## All Eligible Range

| Parameter | Count | Status | Lower | Upper | Median | Mean | p05 | p95 | Units | Entry IDs |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| Km_cellobiose | 15 | ok | 0.68 | 114 | 21 | 31.0733333333 | 4.964 | 86.28 | mM | 35622;38521;38523;38524;38525;38526;38527;39780;39781;39782;39783;39784;44879;44888;60725 |
| kcat_cellobiose | 15 | ok | 0.13 | 7.17 | 2.09 | 2.566 | 0.403 | 5.28 | s^(-1) | 35622;38521;38523;38524;38525;38526;38527;39780;39781;39782;39783;39784;44879;44888;60725 |

## Scoped Groups

| Group type | Group | Parameter | Count | Status | Lower | Upper | Median | Units |
| --- | --- | --- | ---: | --- | ---: | ---: | ---: | --- |
| by_organism | Bacteroides ovatus | Km_cellobiose | 1 | insufficient_n | 0.68 | 0.68 | 0.68 | mM |
| by_organism | Bacteroides ovatus | kcat_cellobiose | 1 | insufficient_n | 1.57 | 1.57 | 1.57 | s^(-1) |
| by_organism | Oryza sativa | Km_cellobiose | 8 | ok | 14.3 | 74.4 | 21.95 | mM |
| by_organism | Oryza sativa | kcat_cellobiose | 8 | ok | 0.13 | 7.17 | 1.14 | s^(-1) |
| by_organism | Phanerochaete chrysosporium | Km_cellobiose | 6 | ok | 6.8 | 114 | 17.15 | mM |
| by_organism | Phanerochaete chrysosporium | kcat_cellobiose | 6 | ok | 1.81 | 4.47 | 3.585 | s^(-1) |
| by_pH_exact | pH 4.5 | Km_cellobiose | 1 | insufficient_n | 19.6 | 19.6 | 19.6 | mM |
| by_pH_exact | pH 4.5 | kcat_cellobiose | 1 | insufficient_n | 0.52 | 0.52 | 0.52 | s^(-1) |
| by_pH_exact | pH 5 | Km_cellobiose | 7 | ok | 14.3 | 74.4 | 22 | mM |
| by_pH_exact | pH 5 | kcat_cellobiose | 7 | ok | 0.13 | 7.17 | 1.16 | s^(-1) |
| by_pH_exact | pH 5.5 | Km_cellobiose | 1 | insufficient_n | 114 | 114 | 114 | mM |
| by_pH_exact | pH 5.5 | kcat_cellobiose | 1 | insufficient_n | 3.23 | 3.23 | 3.23 | s^(-1) |
| by_pH_exact | pH 6 | Km_cellobiose | 2 | ok | 9.22 | 13.3 | 11.26 | mM |
| by_pH_exact | pH 6 | kcat_cellobiose | 2 | ok | 2.53 | 4.35 | 3.44 | s^(-1) |
| by_pH_exact | pH 6.5 | Km_cellobiose | 3 | ok | 6.8 | 46.5 | 21 | mM |
| by_pH_exact | pH 6.5 | kcat_cellobiose | 3 | ok | 1.81 | 4.47 | 3.94 | s^(-1) |
| by_pH_exact | pH 7.6 | Km_cellobiose | 1 | insufficient_n | 0.68 | 0.68 | 0.68 | mM |
| by_pH_exact | pH 7.6 | kcat_cellobiose | 1 | insufficient_n | 1.57 | 1.57 | 1.57 | s^(-1) |
| by_temperature_exact | 30 °C | Km_cellobiose | 13 | ok | 6.8 | 114 | 21.9 | mM |
| by_temperature_exact | 30 °C | kcat_cellobiose | 13 | ok | 0.13 | 7.17 | 2.53 | s^(-1) |
| by_temperature_exact | 37 °C | Km_cellobiose | 1 | insufficient_n | 0.68 | 0.68 | 0.68 | mM |
| by_temperature_exact | 37 °C | kcat_cellobiose | 1 | insufficient_n | 1.57 | 1.57 | 1.57 | s^(-1) |
| by_temperature_exact | 40 °C | Km_cellobiose | 1 | insufficient_n | 19.6 | 19.6 | 19.6 | mM |
| by_temperature_exact | 40 °C | kcat_cellobiose | 1 | insufficient_n | 0.52 | 0.52 | 0.52 | s^(-1) |
| by_organism_and_pH | Bacteroides ovatus \| pH 7.6 | Km_cellobiose | 1 | insufficient_n | 0.68 | 0.68 | 0.68 | mM |
| by_organism_and_pH | Bacteroides ovatus \| pH 7.6 | kcat_cellobiose | 1 | insufficient_n | 1.57 | 1.57 | 1.57 | s^(-1) |
| by_organism_and_pH | Oryza sativa \| pH 4.5 | Km_cellobiose | 1 | insufficient_n | 19.6 | 19.6 | 19.6 | mM |
| by_organism_and_pH | Oryza sativa \| pH 4.5 | kcat_cellobiose | 1 | insufficient_n | 0.52 | 0.52 | 0.52 | s^(-1) |
| by_organism_and_pH | Oryza sativa \| pH 5 | Km_cellobiose | 7 | ok | 14.3 | 74.4 | 22 | mM |
| by_organism_and_pH | Oryza sativa \| pH 5 | kcat_cellobiose | 7 | ok | 0.13 | 7.17 | 1.16 | s^(-1) |
| by_organism_and_pH | Phanerochaete chrysosporium \| pH 5.5 | Km_cellobiose | 1 | insufficient_n | 114 | 114 | 114 | mM |
| by_organism_and_pH | Phanerochaete chrysosporium \| pH 5.5 | kcat_cellobiose | 1 | insufficient_n | 3.23 | 3.23 | 3.23 | s^(-1) |
| by_organism_and_pH | Phanerochaete chrysosporium \| pH 6 | Km_cellobiose | 2 | ok | 9.22 | 13.3 | 11.26 | mM |
| by_organism_and_pH | Phanerochaete chrysosporium \| pH 6 | kcat_cellobiose | 2 | ok | 2.53 | 4.35 | 3.44 | s^(-1) |
| by_organism_and_pH | Phanerochaete chrysosporium \| pH 6.5 | Km_cellobiose | 3 | ok | 6.8 | 46.5 | 21 | mM |
| by_organism_and_pH | Phanerochaete chrysosporium \| pH 6.5 | kcat_cellobiose | 3 | ok | 1.81 | 4.47 | 3.94 | s^(-1) |
| wildtype_only | wildtype_only | Km_cellobiose | 6 | ok | 0.68 | 26 | 17.45 | mM |
| wildtype_only | wildtype_only | kcat_cellobiose | 6 | ok | 0.13 | 1.81 | 1.07 | s^(-1) |
| mutant_only | mutant_only | Km_cellobiose | 9 | ok | 9.22 | 114 | 21.9 | mM |
| mutant_only | mutant_only | kcat_cellobiose | 9 | ok | 1.12 | 7.17 | 3.42 | s^(-1) |

## Warnings

- The Km/kcat ranges pool multiple SABIO-RK Reaction 618 entries across organisms and/or assay conditions.
- Ranges are exploratory literature priors, not selected-entry uncertainty or calibrated environmental response laws.

## Limitations

- No live SABIO-RK API access is required or used by this curation path.
- No unit conversion is applied; accepted source units are preserved.
- Broad cross-entry ranges are not posterior uncertainty estimates.
- Broad cross-entry ranges are not pH or temperature response models.
- The selected exact EntryID 35622 values remain separate registry records.
