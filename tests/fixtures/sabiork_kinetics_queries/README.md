# Synthetic SABIO-RK responses for the kinetics lookup tests (FETCH-002)

**Synthetic test responses written for the tests; not SABIO-RK data. Nothing
here was downloaded from SABIO-RK, no organism stands behind any entry, and no
value is a measurement.**

The files stand in for the bodies of SABIO-RK's kinetic-law export API
(`https://sabio.h-its.org/export-api/sabio/kinlaw-entry/json?q=...&page=1&pageSize=1000`),
in the `{"meta": ..., "data": [...]}` envelope and entry format of the frozen
Reaction 618 export under `data/kinetic_records/sabiork/`, so that
`tests/test_fetch_kinetics.py` can exercise
`fungal_model.sources.sabiork.query_snapshots` and `fungmod assemble
--fetch-kinetics` with `urlopen` patched. The tests never reach the network.
What SABIO-RK returns for these queries, how it matches a compound name, and
its answer to a query without matches were not checked against a live
response, because the environment the tests were written in could not reach
sabio.h-its.org.

| File | Stands in for the answer to | Entries |
| --- | --- | --- |
| `ecnumber_3_2_1_21_cellobiose.json` | `ECNumber:"3.2.1.21" AND Substrate:"Cellobiose"` (the registry `beta_glucosidase` record's EC number and the registry `cellobiose` record's name) | seven, below |
| `ecnumber_3_2_1_3_maltose.json` | `ECNumber:"3.2.1.3" AND Substrate:"maltose"` (the registry `glucoamylase` record's EC number; `maltose` is a substrate the tests describe) | two, below |
| `no_entries.json` | any query without matches (`total_count` 0, assumed format) | none |

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

Everything is invented: the organism names, the EntryIDs 9900001 to 9900012
and the reaction ids 9900100 and 9900200 (placeholders far above the
identifiers SABIO-RK has issued so far), every value, the buffer and the
publication, which is "FungMod test fixture" without a PubMed id. The
compound names "Cellobiose", "Maltose", "H2O", "beta-D-Glucose" and
"D-Glucose" are used because the lookup matches entries to requested
substrates by name; they carry no measured value.
