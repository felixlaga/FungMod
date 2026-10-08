# Synthetic SABIO-RK responses for the kinetics lookup tests (FETCH-002, FETCH-003)

**Synthetic test responses written for the tests; not SABIO-RK data. Nothing
here was downloaded from SABIO-RK, no organism stands behind any entry, and no
value is a measurement.**

The files stand in for the bodies of SABIO-RK's kinetic-law export API
(`https://sabio.h-its.org/export-api/sabio/kinlaw-entry/json?q=...&page=1&pageSize=1000`),
in the `{"meta": ..., "data": [...]}` envelope and entry format of the frozen
Reaction 618 export under `data/kinetic_records/sabiork/`, so that
`tests/test_fetch_kinetics.py` can exercise
`fungal_model.sources.sabiork.query_snapshots` and `fungmod assemble
--fetch-kinetics` with `urlopen` patched (and `tests/test_fetch_kinetics_user_classes.py`
the lookup of classes a user dataset defines, FETCH-003). The tests never reach the network.
What SABIO-RK returns for these queries, how it matches a compound name, and
its answer to a query without matches were not checked against a live
response, because the environment the tests were written in could not reach
sabio.h-its.org.

| File | Stands in for the answer to | Entries |
| --- | --- | --- |
| `ecnumber_3_2_1_21_cellobiose.json` | `ECNumber:"3.2.1.21" AND Substrate:"Cellobiose"` (the registry `beta_glucosidase` record's EC number and the registry `cellobiose` record's name) | seven, below |
| `ecnumber_3_2_1_3_maltose.json` | `ECNumber:"3.2.1.3" AND Substrate:"maltose"` (the registry `glucoamylase` record's EC number; `maltose` is a substrate the tests describe) | two, below |
| `no_entries.json` | any query without matches (`total_count` 0, assumed format) | none |
| `ecnumber_3_1_1_1_nitrophenyl_butyrate.json` | `ECNumber:"3.1.1.1" AND Substrate:"4-Nitrophenyl butyrate"` (the `ec_number` of the user-defined class `lab_ester_hydrolase` and the substrate name of `tests/fixtures/user_data/lab_classes_case/`) | four, below |
| `ecnumber_3_1_3_2_nitrophenyl_phosphate.json` | `ECNumber:"3.1.3.2" AND Substrate:"4-Nitrophenyl phosphate"` (the user-defined class `lab_phosphomonoesterase` of the same dataset) | two, below |

The tests derive further answers from these in memory: the first file split
into two pages (`total_pages` 2), a page whose `total_count` exceeds its
entries (a truncated answer), a changed value (a superseded answer), and HTTP
errors.

Entries of `ecnumber_3_2_1_21_cellobiose.json` (EC 3.2.1.21, all in vitro):

| EntryID | Organism | Condition | Content | Outcome in the tests |
| --- | --- | --- | --- | --- |
| 9900001 | Synthetic kinetics organism K1 | 30 °C, pH 5 | kcat 12 ± 1 s^(-1), Km 2.5 ± 0.2 mM, substrate 0.5 to 20 mM | literature of a fungus declared to be K1; a transfer otherwise |
| 9900002 | Synthetic kinetics organism K2 | 30 °C, pH 5 | kcat 30 ± 2 s^(-1), Km 1.1 ± 0.1 mM | a transfer; with 9900001 a conflict when neither is the fungus's species |
| 9900003 | Synthetic kinetics organism K3 | 45 °C, pH 6 | kcat 50 s^(-1), Km 0.9 mM | measured at a condition that is not requested |
| 9900004 | Synthetic kinetics organism K2 | 30 °C, pH 5 | mutant ("synthetic variant V1") | not convertible (mutant) |
| 9900005 | Synthetic kinetics organism K3 | 30 °C, pH 5 | kcat and Km in "arbitrary units" | not convertible (units not parsed) |
| 9900006 | Synthetic kinetics organism K3 | 30 °C, pH 5 | Km of "Synthetic acceptor A9" | not used (another substrate) |
| 9900007 | Synthetic kinetics organism K2 | 30 °C, pH 5 | kcat/Km only | not convertible (no Km, kcat or Vmax) |

Entries of `ecnumber_3_2_1_3_maltose.json` (EC 3.2.1.3, the Vmax form):

| EntryID | Organism | Condition | Content | Outcome in the tests |
| --- | --- | --- | --- | --- |
| 9900011 | Synthetic kinetics organism K4 | 40 °C, pH 4.5 | Vmax 0.8 ± 0.05 mM*min^(-1), Km 3.2 ± 0.3 mM | a transfer (estimates) |
| 9900012 | Synthetic kinetics organism K5 | 25 °C, pH 7 | Vmax 1.6 mM*min^(-1), Km 1.9 mM | measured at a condition that is not requested |

Entries of `ecnumber_3_1_1_1_nitrophenyl_butyrate.json` (EC 3.1.1.1, the kcat form; FETCH-003):

| EntryID | Organism | Condition | Content | Outcome in the tests |
| --- | --- | --- | --- | --- |
| 9900021 | Synthetic kinetics organism K6 | 30 °C, pH 7 | kcat 45 ± 3 s^(-1), Km 0.35 ± 0.04 mM, substrate 0.05 to 2 mM | literature of strain K6 (its species) for its lab class |
| 9900022 | Synthetic kinetics organism K7 | 37 °C, pH 7.5 | kcat 60 ± 4 s^(-1), Km 0.52 ± 0.05 mM | a transfer (estimates) |
| 9900023 | Synthetic kinetics organism K7 | 30 °C, pH 7 | mutant ("synthetic variant V2") | not convertible (mutant) |
| 9900024 | Synthetic kinetics organism K6 | 25 °C, pH 7 | kcat 30 s^(-1), Km 0.42 mM | listed: the lab's own rows at that condition come first |

Entries of `ecnumber_3_1_3_2_nitrophenyl_phosphate.json` (EC 3.1.3.2, the Vmax form in micromolar units; FETCH-003):

| EntryID | Organism | Condition | Content | Outcome in the tests |
| --- | --- | --- | --- | --- |
| 9900031 | Synthetic kinetics organism K8 | 40 °C, pH 5 | Vmax 85 ± 5 µM*min^(-1), Km 210 ± 20 µM | a transfer (estimates) |
| 9900032 | Synthetic kinetics organism K8 | 25 °C, pH 5.5 | Vmax 40 µM*min^(-1), Km 180 µM | measured at a condition that is not requested |

Everything is invented: the organism names, the EntryIDs 9900001 to 9900032
and the reaction ids 9900100, 9900200, 9900300 and 9900400 (placeholders far
above the identifiers SABIO-RK has issued so far), every value, the buffer and
the publication, which is "FungMod test fixture" without a PubMed id. The
compound names "Cellobiose", "Maltose", "H2O", "beta-D-Glucose",
"D-Glucose", "4-Nitrophenyl butyrate", "4-Nitrophenyl phosphate",
"4-Nitrophenol", "Butanoate" and "Orthophosphate" and the enzyme names are
used because the lookup matches entries to requested substrates by name; they
carry no measured value. The FETCH-003 files were generated by a short script
from the entry format of the FETCH-002 files (2-space JSON, UTF-8, a final
newline); the tests compare stored raw pages with these exact bytes.
