# From a fungus name to a simulation

This page walks through the whole route from a request such as "fungus X on
substrate Y at conditions Z" to degradation dynamics over time, from a shell:

1. **Assemble** a draft dataset: FungMod finds the fungus's UniProt reference
   proteome by name, takes its enzyme classes from that proteome, looks up the
   kinetics of each class in SABIO-RK by EC number, and writes one reviewable
   draft with a report of what is known, from where, and what is missing.
2. **Choose** between conflicting sources where the report shows a conflict.
3. **Fill** the `REVIEW:` fields, the decisions FungMod leaves to you.
4. **Check** the reviewed dataset with `fungmod check-data`.
5. **Run** the virtual experiment with `fungmod run --runnable-only`, which
   simulates every case that has what it needs and lists the others with
   their measurement requests.
6. **Read** the outputs: metrics, rates, threshold times, provenance,
   limitations and measurement requests.
7. **Replace** the estimates with your own measurements as you obtain them.

FungMod never fills a gap by itself along this route: kinetics measured on
another organism's enzyme stay estimates, kinetics are never reused at another
temperature or pH without a response law, and a case without kinetics is a
gap with a measurement request, not a case left out.

!!! warning "The data on this page are synthetic test fixtures, not biology"

    The organism "Synthetic fixture mould B2", its proteome `UP999990002`,
    the SABIO-RK entries 9900001 to 9900007 and their organisms "Synthetic
    kinetics organism K1" to "K3" were written by hand in the services'
    formats for FungMod's tests (`tests/fixtures/uniprot_proteome_search/`
    and `tests/fixtures/sabiork_kinetics_queries/`); none is UniProt or
    SABIO-RK data, no organism stands behind them and no value is a
    measurement. The initial cellobiose and enzyme concentrations below are
    design choices made for this page. Every printed output on this page is real output of the
    commands shown, run in a repository checkout on frozen snapshots of those
    synthetic responses (`tests/fixtures/walkthrough/`);
    `tests/test_walkthrough_doc.py` reruns the commands and checks every line
    shown (`...` marks omitted text). A run for a real fungus needs network
    access (`--fetch`), and the live service formats are not yet verified
    (see [verifying the live lookups](#verifying-the-live-lookups)).

## 1. Assemble the draft

For your own fungus, on a machine with internet access:

```bash
fungmod assemble --fungus "Genus species" \
  --substrate cellobiose --temperature-c 30 --temperature-c 40 --ph 5 \
  --fetch-proteome --fetch-kinetics --network --fetch \
  --design substrate_initial_concentration=10 mM --time-grid 10 hour 61 \
  --dataset-id my_fungus --output my_fungus
```

| Option | What it does |
| --- | --- |
| `--fungus NAME` | The fungus of this draft (one per call). Without `--scientific-name` it is also the name searched in UniProt. |
| `--scientific-name NAME` | The species, when `--fungus` is your strain's own name: it is the name searched in UniProt, and SABIO-RK entries of this organism count as the fungus's own species (literature rather than a transfer). |
| `--substrate`, `--temperature-c`, `--ph` | The request: substrates by name (repeatable), and a grid of conditions in which every temperature (degC) and pH pair is one condition. |
| `--fetch-proteome` | Takes the enzyme repertoire from the UniProt reference proteome found under the name: the one candidate whose organism name equals it, or the only candidate of the search. Anything else is refused with every candidate listed; choose one with `--proteome UP...`. No kinetic value comes from a proteome. |
| `--fetch-kinetics` | Looks up the kinetics of every class of that repertoire acting on a requested substrate in SABIO-RK: one query per EC number of the class's registry record and the substrate's name, `ECNumber:"<EC number>" AND Substrate:"<substrate name>"`. |
| `--network` | Drafts one [enzyme network](user-data.md#several-enzymes-acting-together) instead of one case per class: every class acting on the substrate, or on a pool it releases through a stated product, acts together, and the network runs at a condition only when every member has kinetics there. |
| `--fetch` | **The network opt-in.** Only with it does the command reach UniProt and SABIO-RK; each response is parsed before it is stored and frozen as a digest-checked snapshot, so the same command without `--fetch` reruns offline and writes the same draft byte for byte. Without it only the snapshots are read, and a missing one is refused with the command that fetches it. A new response that differs from a stored snapshot is refused and the snapshot kept. |
| `--design`, `--time-grid` | The virtual assay's own amounts (here the initial cellobiose concentration) and the simulation time grid. Without them they are `REVIEW:` fields; kinetic constants never come from them. |
| `--snapshot-dir`, `--cache-dir` | Where the UniProt and SABIO-RK snapshots are read and stored (default `data/source_snapshots/uniprot` and `data/source_snapshots/sabiork`, relative to the current directory). |
| `--dataset-id`, `--output` | The draft's id and a new or empty directory; nothing is overwritten. |

The worked example runs the same command for the synthetic organism, in a
repository checkout, without `--fetch`: the two snapshot directories already
hold the frozen answers, so nothing is fetched.

<!-- walkthrough-command: assemble-first -->
```bash
fungmod assemble --fungus "Synthetic fixture mould B2" \
  --substrate cellobiose --temperature-c 30 --temperature-c 40 --ph 5 \
  --fetch-proteome --fetch-kinetics --network \
  --design substrate_initial_concentration=10 mM --time-grid 10 hour 61 \
  --snapshot-dir tests/fixtures/walkthrough/uniprot \
  --cache-dir tests/fixtures/walkthrough/sabiork \
  --dataset-id mould_b2 --output mould_b2_first
```

<!-- walkthrough-output: assemble-first -->
```text
Proteome of the fungus (UniProt):
  network: not used; frozen snapshots under tests/fixtures/walkthrough/uniprot (--fetch queries UniProt)
  name searched: 'Synthetic fixture mould B2' (from --fungus)
  search: organism_name:"Synthetic fixture mould B2" AND proteome_type:1 -> 1 candidate(s); snapshot tests/fixtures/walkthrough/uniprot/organism_name_synthetic_fixture_mould_b2_32e605c891b0 (SHA-256 80ee05ef...; retrieved 2026-10-08T11:37:25.872090Z; UniProt release fixture_release)
    #  proteome     organism                                   taxonomy    type                                  proteins
    1  UP999990002  Synthetic fixture mould B2 (strain FIX-2)  9000000002  reference proteome (proteome_type:1)  5         chosen
  chosen: UP999990002 (Synthetic fixture mould B2 (strain FIX-2)) because it is the only candidate of the search
  export: (proteome:UP999990002), 5 UniProtKB entries of Synthetic fixture mould B2 (strain FIX-2); snapshot tests/fixtures/walkthrough/uniprot/proteome_UP999990002 (SHA-256 f239200d...; retrieved 2026-10-08T11:37:25.872936Z; UniProt release fixture_release)

Assembled draft: mould_b2
  fungus 'Synthetic fixture mould B2' -> Synthetic fixture mould B2 (strain synthetic_fixture_mould_b2, new_strain)
  substrate 'cellobiose' -> Cellobiose (cellobiose, registry)
  condition c30_ph5: 30 degC, pH 5 (conditions.csv)
  condition c40_ph5: 40 degC, pH 5 (conditions.csv)

Enzyme classes of the fungus: 3
  class             declared in  evidence
  beta_glucosidase  genomes.csv  UniProt proteome UP999990002 (1 protein, EC 3.2.1.21)
  chitinase         genomes.csv  UniProt proteome UP999990002 (1 protein, CAZy families GH18, EC 3.2.1.14)
  endo_xylanase     genomes.csv  UniProt proteome UP999990002 (1 protein, CAZy families GH11, EC 3.2.1.8)
Annotated classes without a registry record (no case is assembled for them):
  - lytic_polysaccharide_monooxygenase (families AA9): no enzyme-class record in the registry; FungMod does not create one from a proteome export, so no case is assembled for it
Annotated families without an enzyme class:
  - CBM18: the curated CAZy family map assigns no enzyme class to this family
EC numbers of the proteome without a registry class (listed, not resolved):
  - 3.1.1.1 (1 protein(s)): no registry enzyme class carries this EC number
On Cellobiose (cellobiose): acting classes beta_glucosidase
  not acting: chitinase: substrate class 'cellobiose' is not among the class's substrate classes ['chitin']
  not acting: endo_xylanase: substrate class 'cellobiose' is not among the class's substrate classes ['xylan']

Enzyme network (--network; user_dataset.yml enzyme_network, entry substrates cellobiose): the member classes act together, all or nothing per condition
  from cellobiose: cellobiose -> beta_D_glucose (yield under review, final product)
  member class      pool                c30_ph5   c40_ph5
  beta_glucosidase  cellobiose (entry)  conflict  gap
  c30_ph5: blocked (initial concentration of cellobiose: stated): beta_glucosidase on cellobiose (conflict)
  c40_ph5: blocked (initial concentration of cellobiose: stated): beta_glucosidase on cellobiose (gap)
  not a member (acts on no pool of this network): chitinase: cellobiose: substrate class 'cellobiose' is not among the class's substrate classes ['chitin']
  not a member (acts on no pool of this network): endo_xylanase: cellobiose: substrate class 'cellobiose' is not among the class's substrate classes ['xylan']

Kinetics looked up by EC number (--fetch-kinetics; SABIO-RK https://sabio.h-its.org/export-api/sabio/kinlaw-entry/json, one query per EC number of a class and substrate name: ECNumber:"<EC number>" AND Substrate:"<substrate name>")
  network: not used; frozen snapshots under tests/fixtures/walkthrough/sabiork (--fetch queries the database)
  beta_glucosidase on cellobiose, EC 3.2.1.21: ECNumber:"3.2.1.21" AND Substrate:"Cellobiose"
    snapshot ecnumber_3.2.1.21_and_substrate_cellobiose-5a9fabef44f3/20261008T113726078755Z-d68ba850915349b5b7c16eec90867694 (retrieved 2026-10-08T11:37:26.081315Z, HTTP 200, raw SHA-256 846c8df5...): 7 entries; 3 listed, 1 not used, 3 not convertible
    listed 9900001 (Synthetic kinetics organism K1): SABIO-RK EntryID 9900001 (Synthetic kinetics organism K1), SABIO-RK EntryID 9900002 (Synthetic kinetics organism K2) all give kinetics for beta-glucosidase on Cellobiose at 30 degC, pH 5; FungMod holds one value per quantity and case and does not choose between them (select one with entry_ids)
    listed 9900002 (Synthetic kinetics organism K2): ...
    listed 9900003 (Synthetic kinetics organism K3): no kinetics at 40 degC, pH 5; kinetics are stated only at other conditions (...), which FungMod does not reuse here without a response law
    not convertible 9900004 (Synthetic kinetics organism K2): mutant enzyme (synthetic variant V1): an engineered variant, not an enzyme of Synthetic kinetics organism K2, so it is not entered as the organism's kinetics
    not convertible 9900005 (Synthetic kinetics organism K3): no Km, kcat or Vmax could be converted (its parameters are listed under Parameters not converted)
      parameter kcat (7 arbitrary units): units 'arbitrary units' are not parsed by the unit registry and are not in the SABIO-RK unit table
      parameter Km (1.0 arbitrary units): units 'arbitrary units' are not parsed by the unit registry and are not in the SABIO-RK unit table
    not used 9900006 (Synthetic kinetics organism K3): its substrate 'Synthetic acceptor A9' is not a requested substrate
    not convertible 9900007 (Synthetic kinetics organism K2): no Km, kcat or Vmax could be converted (its parameters are listed under Parameters not converted)
      parameter kcat_Km (11 mM^(-1)*s^(-1)): kcat/Km is not a user-data quantity; FungMod never derives Km or kcat from it

Cases: 2 (enzyme class x substrate x condition)
  #  fungus                      class             substrate   condition  kinetics status  route  source ids
  1  Synthetic fixture mould B2  beta_glucosidase  cellobiose  c30_ph5    conflict         none   SABIO-RK EntryID 9900001; SABIO-RK EntryID 9900002
  2  Synthetic fixture mould B2  beta_glucosidase  cellobiose  c40_ph5    gap              none   SABIO-RK EntryID 9900001; SABIO-RK EntryID 9900002; SABIO-RK EntryID 9900003
  case 1: SABIO-RK EntryID 9900001 (Synthetic kinetics organism K1), SABIO-RK EntryID 9900002 (Synthetic kinetics organism K2) all give kinetics for beta-glucosidase on Cellobiose at 30 degC, pH 5; FungMod holds one value per quantity and case and does not choose between them (select one with entry_ids)
  case 2: no kinetics at 40 degC, pH 5; kinetics are stated only at other conditions (...), which FungMod does not reuse here without a response law

Kinetic-law entries considered: 7
  entry    organism                        use              reason
...

Limitations of this draft:
  - One fungus per call; its enzyme repertoire comes only from its genome annotation or proteome export, the classes you assert, its own rows in a user dataset, or its registry record.
...
  - Kinetics transferred from another organism's enzyme are estimates (exploratory mode only). FungMod never labels them literature or measured for this fungus; only you can change that, by editing kinetics.csv with your own evidence.
  - A genome annotation or proteome export states which enzyme classes the fungus can encode; no rate, concentration, expression or secretion is taken from it.
...
  - The query form, the ECNumber and Substrate fields and SABIO-RK's answer to a query without matches were not checked against a live response when the lookup was written. An answer that is not the kinetic-law export envelope, or whose entry count differs from its total_count, is refused and nothing is stored.
  - Enzyme network draft: the member classes act together as independent Michaelis-Menten processes whose rates add on shared pools; no synergy, no competition for substrate binding or adsorption sites, and no inhibition unless a ki row states a competitive inhibitor.
...

Draft written to mould_b2_first:
  annotations/proteome_UP999990002.tsv
  conditions.csv
  enzymes.csv
  genomes.csv
  kinetics.csv
  review.md
  strains.csv
  substrates.csv
  user_dataset.yml

Fields to fill (3); check-data refuses the directory until each REVIEW: field is filled:
  user_dataset.yml:-:contributor: REVIEW: name of the person who reviewed these tables
  substrates.csv:2:product_yield: REVIEW: mol of product per mol of Cellobiose; no source settles the stoichiometry
  substrates.csv:2:source: REVIEW: the reaction or source stating the product and its yield

Next:
  1. Fill the 3 REVIEW: field(s) above; mould_b2_first/review.md explains every decision.
  2. fungmod check-data mould_b2_first
  3. Run it (exploratory mode samples ranges and estimates; scientific mode takes exact measured, literature or design values only):
     fungmod run --user-data mould_b2_first --fungus 'Synthetic fixture mould B2' --substrate cellobiose --condition c30_ph5 --condition c40_ph5 --runnable-only \
       --mode exploratory --samples N --seed S --output RUN_DIR
     --runnable-only because 2 enzyme-network case(s) of this command are blocked (...): a network runs at a condition only when every member class has kinetics and its entry an initial concentration, so the preflight blocks these, and without the flag nothing is simulated (exit code 3); with it the runnable network cases are simulated and the blocked ones are listed with their measurement requests (exit code 4; 3 when none is runnable).
```

Read the report from the top:

- **Proteome.** The name was searched among UniProt's reference proteomes;
  the search had one candidate, whose organism name adds a strain, so it was
  taken under the only-candidate rule (an exact name match is the other rule;
  several candidates without one exact match are refused with all of them
  listed). The export (5 proteins) is copied into the draft as
  `annotations/proteome_UP999990002.tsv`, which its `genomes.csv` row names.
- **Enzyme classes.** EC numbers and CAZy families resolve to registry
  classes: `beta_glucosidase`, `chitinase` and `endo_xylanase`. What the
  registry cannot model is listed, not invented: the class of the AA9
  protein (a lytic polysaccharide monooxygenase) has no registry record,
  CBM18 maps to no class, and EC 3.1.1.1 resolves to no class.
- **Which classes act.** Only `beta_glucosidase` acts on cellobiose by the
  registry's categorical rule; the other two are listed with the reason.
- **The network.** Cellobiose is the entry pool and releases
  `beta_D_glucose`, the registry record's single product. The one member is
  blocked at both conditions, by a conflict at 30 degC and a gap at 40 degC.
- **Kinetics looked up by EC number.** One query, EC 3.2.1.21 and
  "Cellobiose" (the registry record's name). Each of the 7 entries is
  accounted for: two of other organisms at 30 degC, one at 45 degC and pH 6
  (not a requested condition), a mutant, two entries with nothing
  convertible, and one entry whose kinetics are for another substrate.
- **Cases.** One row per class, substrate and condition, with its kinetics
  status, how the condition is reached (`route`) and the sources.
- **Fields to fill.** The decisions left to you; `check-data` refuses the
  draft until each is made. Here the product yield is open because no entry
  was converted, so no reaction states the stoichiometry yet.
- **Next.** The exact commands to check and run the draft; `--runnable-only`
  because cases are blocked.

The kinetics status of a case is one of:

| `kinetics status` | Source | What the draft holds | In this example |
| --- | --- | --- | --- |
| `user_data` | Your own dataset's rows for this strain, class, substrate and condition (`--user-data`). | Your rows, unchanged, with your evidence types. They take precedence over everything below. | Not used here; see [step 7](#7-replace-estimates-with-your-own-measurements). |
| `literature_same_organism` | One SABIO-RK entry whose organism is the fungus's species (`--scientific-name`, or an organism you name with `--same-species`). | The entry converted as literature. | None of the synthetic entries is of this organism (see the [`--fetch-kinetics` example](cli.md#kinetics-looked-up-by-ec-number-fetch-kinetics) for one). |
| `transferred_estimate` | One SABIO-RK entry of another organism. | The same conversion, every value except the assay's design amounts written as an `estimate` with the method "transferred from ...". Exploratory mode only. | 30 degC after [step 2](#2-resolve-a-conflict-choose-an-entry). |
| `conflict` | Several candidates of the same standing at one condition. | Nothing; all are listed. Choose one with `--entry-id`. | 30 degC: entries 9900001 and 9900002. |
| `gap` | No candidate at this condition. | No kinetic constant; once loaded, explicit unknowns with measurement requests. | 40 degC: no entry states it, and none is reused from another temperature. |

## 2. Resolve a conflict: choose an entry

FungMod does not choose between the two 30 degC entries: both are transfers
from other organisms, of the same standing. Choosing is a scientific
decision: which organism's enzyme is the better stand-in, under which assay
conditions, from which publication. These synthetic entries carry no such
evidence, so this page picks 9900001 only to continue the example. A draft
directory is never overwritten, so the choice goes into a new `--output`:

<!-- walkthrough-command: assemble-entry -->
```bash
fungmod assemble --fungus "Synthetic fixture mould B2" \
  --substrate cellobiose --temperature-c 30 --temperature-c 40 --ph 5 \
  --fetch-proteome --fetch-kinetics --network --entry-id 9900001 \
  --design substrate_initial_concentration=10 mM --time-grid 10 hour 61 \
  --snapshot-dir tests/fixtures/walkthrough/uniprot \
  --cache-dir tests/fixtures/walkthrough/sabiork \
  --dataset-id mould_b2 --output mould_b2
```

<!-- walkthrough-output: assemble-entry -->
```text
...
Enzyme network (--network; user_dataset.yml enzyme_network, entry substrates cellobiose): the member classes act together, all or nothing per condition
  from cellobiose: cellobiose -> beta_D_glucose (2 mol/mol, final product)
  member class      pool                c30_ph5               c40_ph5
  beta_glucosidase  cellobiose (entry)  transferred_estimate  gap
  c30_ph5: all_members_have_kinetics (initial concentration of cellobiose: stated)
  c40_ph5: blocked (initial concentration of cellobiose: stated): beta_glucosidase on cellobiose (gap)
...
  beta_glucosidase on cellobiose, EC 3.2.1.21: ECNumber:"3.2.1.21" AND Substrate:"Cellobiose"
    snapshot ecnumber_3.2.1.21_and_substrate_cellobiose-5a9fabef44f3/20261008T113726078755Z-d68ba850915349b5b7c16eec90867694 (retrieved 2026-10-08T11:37:26.081315Z, HTTP 200, raw SHA-256 846c8df5...): 7 entries; 1 converted, 6 not selected
    converted 9900001 (Synthetic kinetics organism K1) -> beta_glucosidase on cellobiose at c30_ph5 (transferred_estimate), beta_glucosidase on cellobiose at c40_ph5 (gap)
    not selected 9900002 (Synthetic kinetics organism K2): not selected by entry_ids
...

Cases: 2 (enzyme class x substrate x condition)
  #  fungus                      class             substrate   condition  kinetics status       route           source ids
  1  Synthetic fixture mould B2  beta_glucosidase  cellobiose  c30_ph5    transferred_estimate  same_condition  SABIO-RK EntryID 9900001
  2  Synthetic fixture mould B2  beta_glucosidase  cellobiose  c40_ph5    gap                   none            SABIO-RK EntryID 9900001
  case 1: transferred from Synthetic kinetics organism K1 enzyme, SABIO-RK entry 9900001: a cross-organism transfer, written as estimates for Synthetic fixture mould B2 (exploratory mode only)
  case 2: kinetics for beta-glucosidase on Cellobiose are stated only at c30_ph5 (30 degC, pH 5; SABIO-RK EntryID 9900001 (Synthetic kinetics organism K1)); FungMod does not reuse them at 40 degC, pH 5 without a temperature response law, so this condition is a gap whose measurement requests name c30_ph5
Transferred from another organism (estimates, exploratory mode only): entries 9900001
...
Fields to fill (4); check-data refuses the directory until each REVIEW: field is filled:
  user_dataset.yml:-:contributor: REVIEW: name of the person who reviewed these tables
  kinetics.csv:5:value: REVIEW: enzyme concentration of beta-glucosidase in the simulated Cellobiose system (amount per volume), the virtual experiment's own amount; or pass design={'enzyme_concentration': ...}
  kinetics.csv:5:units: REVIEW: an amount-per-volume unit such as uM
  kinetics.csv:5:source: REVIEW: where the enzyme concentration of the virtual experiment comes from

Next:
  1. Fill the 4 REVIEW: field(s) above; mould_b2/review.md explains every decision.
  2. fungmod check-data mould_b2
  3. Run it (exploratory mode samples ranges and estimates; scientific mode takes exact measured, literature or design values only):
     fungmod run --user-data mould_b2 --fungus 'Synthetic fixture mould B2' --substrate cellobiose --condition c30_ph5 --condition c40_ph5 --runnable-only \
       --mode exploratory --samples N --seed S --output RUN_DIR
...
```

The 30 degC case is now a `transferred_estimate`: entry 9900001's Km and
kcat are written to `kinetics.csv` as estimates whose method begins
"transferred from Synthetic kinetics organism K1 enzyme, SABIO-RK entry
9900001", so they run in exploratory mode only. The 40 degC case stays a
gap: the entry states its kinetics at 30 degC, and FungMod does not carry
them to 40 degC without a temperature response law. The converted entry's reaction
states the stoichiometry, so the product yield (2 mol/mol) is no longer a
review field. The kcat form needs the enzyme concentration of the virtual
assay, which no source states: that is a new review field.

## 3. Fill the REVIEW: fields

`mould_b2/review.md` lists every field with what to decide, and explains
every case, transfer, gap and SABIO-RK entry of the draft. Until each field
is filled, `check-data` refuses the directory and lists them all (exit
code 2):

<!-- walkthrough-command: check-unreviewed -->
```bash
fungmod check-data mould_b2
```

<!-- walkthrough-output: check-unreviewed -->
```text
fungmod check-data: error: User dataset 'mould_b2' still has unfilled review fields (cells or manifest values beginning with 'REVIEW:'). 4 issue(s):
  user_dataset.yml:-:contributor: Unfilled review field contributor: 'REVIEW: name of the person who reviewed these tables'. Replace it with a reviewed value before loading.
  kinetics.csv:5:value: Unfilled review field value: "REVIEW: enzyme concentration of beta-glucosidase in the simulated Cellobiose system (amount per volume), the virtual experiment's own amount; or pass design={'enzyme_concentration': ...}". Replace it with a reviewed value before loading.
  kinetics.csv:5:units: Unfilled review field units: 'REVIEW: an amount-per-volume unit such as uM'. Replace it with a reviewed value before loading.
  kinetics.csv:5:source: Unfilled review field source: 'REVIEW: where the enzyme concentration of the virtual experiment comes from'. Replace it with a reviewed value before loading.
  Fill each REVIEW: field (a drafted directory's review.md says what to decide for each), then run fungmod check-data again.
```

Edit the files. In `mould_b2/user_dataset.yml`, the reviewer:

<!-- walkthrough-edit: contributor -->
```yaml
contributor: Your Name
```

In `mould_b2/kinetics.csv`, row 5 (the header is row 1) is the enzyme
concentration of the virtual assay. As drafted:

<!-- walkthrough-file: kinetics-row-5 -->
```text
synthetic_fixture_mould_b2,beta_glucosidase,cellobiose,c30_ph5,enzyme_concentration,"REVIEW: enzyme concentration of beta-glucosidase in the simulated Cellobiose system (amount per volume), the virtual experiment's own amount; or pass design={'enzyme_concentration': ...}",,,REVIEW: an amount-per-volume unit such as uM,design,experimental design,REVIEW: where the enzyme concentration of the virtual experiment comes from,,,,,
```

After review (0.1 uM is a design choice of this page, not a measured
amount):

<!-- walkthrough-edit: kinetics-row-5 -->
```text
synthetic_fixture_mould_b2,beta_glucosidase,cellobiose,c30_ph5,enzyme_concentration,0.1,,,uM,design,experimental design,Virtual assay design: an enzyme concentration chosen for this walkthrough,,,,,
```

Passing `--design enzyme_concentration=0.1 uM` to `assemble` would have
filled this row instead. Decide every field yourself: a `REVIEW:` field is
where FungMod has no source and does not guess.

## 4. Check the dataset

<!-- walkthrough-command: check-reviewed -->
```bash
fungmod check-data mould_b2
```

<!-- walkthrough-output: check-reviewed -->
```text
User dataset: mould_b2
Digest: 289b9673a68f1d4869964583871068da22302a8b3683b20f461b377a4242e7cb
Directory: .../mould_b2
Base registry: .../data_registry/registry_index.yml (registry toy_registry)
Simulation time grid: 10 hour, 61 points
...
Kinetic values: 5; gaps: 3
Gaps (explicit unknowns; preflight reports their cases as underparameterized):
  - mould_b2__network__cellobiose__synthetic_fixture_mould_b2__c40_ph5__km__beta_glucosidase__cellobiose__gap
    measurement request: Measure km of beta-glucosidase from Synthetic fixture mould B2 on Cellobiose at 40 degC, pH 5 (mM); kinetics.csv states kinetic constants of this strain, enzyme class and substrate only at c30_ph5 (30 degC, pH 5), and FungMod does not reuse kinetics measured at another condition; the class was inferred from UniProt proteome UP999990002 (accessions X9B2P001; EC 3.2.1.21; 0 of 1 reviewed in Swiss-Prot).
  - mould_b2__network__cellobiose__synthetic_fixture_mould_b2__c40_ph5__kcat__beta_glucosidase__cellobiose__gap
    measurement request: Measure kcat of beta-glucosidase from Synthetic fixture mould B2 on Cellobiose at 40 degC, pH 5 (units of 1/time); ...
  - mould_b2__network__cellobiose__synthetic_fixture_mould_b2__c40_ph5__enzyme_initial_concentration__beta_glucosidase__gap
    measurement request: Measure or specify the beta-glucosidase concentration from Synthetic fixture mould B2 in the Cellobiose assay at 40 degC, pH 5 (mM); ...
Genome and proteome annotations (genomes.csv): 1
...
Enzyme networks (user_dataset.yml enzyme_network; the classes act together on shared pools, enzyme_network): 1
  from cellobiose: cellobiose -> beta_D_glucose (2 mol/mol); strains synthetic_fixture_mould_b2
  enzyme class      pool        rate form  competitive inhibitor
  beta_glucosidase  cellobiose  kcat       none
```

The dataset loads. Its digest (SHA-256 over the manifest and tables) is
recorded in every run's manifest. The gaps of 40 degC are explicit unknowns,
each with a measurement request naming the fungus, the class, the substrate,
the condition, the units and the evidence for the class (the proteome
accession).

## 5. Run it

<!-- walkthrough-command: run -->
```bash
fungmod run --user-data mould_b2 --fungus "Synthetic fixture mould B2" \
  --substrate cellobiose --condition c30_ph5 --condition c40_ph5 --runnable-only \
  --mode exploratory --samples 8 --seed 1 --output runs/mould_b2
```

<!-- walkthrough-output: run -->
```text
Registry: .../data_registry/registry_index.yml (registry toy_registry, version 0.1.0, maturity development)
User dataset: mould_b2 (digest 289b9673a68f1d4869964583871068da22302a8b3683b20f461b377a4242e7cb), overlaid in memory
  fungus 'Synthetic fixture mould B2' -> mould_b2__synthetic_fixture_mould_b2 (Synthetic fixture mould B2)
  substrate 'cellobiose' -> cellobiose (Cellobiose)
  environment 'c30_ph5' -> mould_b2__c30_ph5 (mould_b2 condition c30_ph5 (30 degC, pH 5))
  environment 'c40_ph5' -> mould_b2__c40_ph5 (mould_b2 condition c40_ph5 (40 degC, pH 5))
Cases: 1 fungus x 1 substrate x 2 environment = 2

Preflight in exploratory mode:
  #  fungus                                substrate   environment        status              runnable
  1  mould_b2__synthetic_fixture_mould_b2  cellobiose  mould_b2__c30_ph5  modelable           yes
  2  mould_b2__synthetic_fixture_mould_b2  cellobiose  mould_b2__c40_ph5  underparameterized  no
  case 2:
    missing parameter mould_b2__network__cellobiose__km__beta_glucosidase__cellobiose; suggested experiment: Measure km of beta-glucosidase from Synthetic fixture mould B2 on Cellobiose at 40 degC, pH 5 (mM); ...
    missing parameter mould_b2__network__cellobiose__kcat__beta_glucosidase__cellobiose; suggested experiment: Measure kcat of beta-glucosidase from Synthetic fixture mould B2 on Cellobiose at 40 degC, pH 5 (units of 1/time); ...
    missing parameter mould_b2__network__cellobiose__enzyme_initial_concentration__beta_glucosidase; suggested experiment: Measure or specify the beta-glucosidase concentration from Synthetic fixture mould B2 in the Cellobiose assay at 40 degC, pH 5 (mM); ...
    blocked: missing_inputs; next action: measure_or_curate_missing_inputs

Not runnable: 1 of 2 case(s) cannot be simulated in exploratory mode.
--runnable-only: simulating the 1 runnable case(s); the blocked case(s) are not simulated and are listed in case_summary.csv as not_simulated, with their missing inputs in missing_parameters.csv and their measurement requests in suggested_experiments.csv.
Measurement requests:
  - Measure km of beta-glucosidase from Synthetic fixture mould B2 on Cellobiose at 40 degC, pH 5 (mM); ...
  - Measure kcat of beta-glucosidase from Synthetic fixture mould B2 on Cellobiose at 40 degC, pH 5 (units of 1/time); ...
  - Measure or specify the beta-glucosidase concentration from Synthetic fixture mould B2 in the Cellobiose assay at 40 degC, pH 5 (mM); ...

Simulated 1 case(s) in exploratory mode: 8 sample(s) per case, seed 1.
Partial run: 1 of 2 requested case(s) simulated; the others were blocked by the preflight.
Run label: exploratory_uncertainty_screen

Case case_0000: mould_b2__synthetic_fixture_mould_b2 + cellobiose + mould_b2__c30_ph5
  samples: 8 simulated, 0 failed
  environment effect: condition_specific_parameters
  environment guardrail: Environment comparisons are allowed for this status with documented limitations.
  Final metrics (median [5th, 95th percentile] over samples):
    final_substrate_remaining          1.708e-05 [1.708e-05, 1.708e-05] millimolar (n=8)
    final_substrate_degraded_fraction  1 [1, 1] dimensionless (n=8)
    final_product_concentration        20 [20, 20] millimolar (n=8)
    final_product_formed               20 [20, 20] millimolar (n=8)
    final_product_yield                2 [2, 2] dimensionless (n=8)
    maximum_product_release_rate       6.912 [6.912, 6.912] millimolar / hour (n=8)
    maximum_substrate_depletion_rate   3.456 [3.456, 3.456] millimolar / hour (n=8)
  Threshold times (median [5th, 95th percentile] over samples):
    time_to_10_percent_substrate_degradation  0.2927 [0.2927, 0.2927] hour (n=8)
    time_to_50_percent_substrate_degradation  1.559 [1.559, 1.559] hour (n=8)
    time_to_90_percent_substrate_degradation  3.419 [3.419, 3.419] hour (n=8)

Case case_0001: mould_b2__synthetic_fixture_mould_b2 + cellobiose + mould_b2__c40_ph5
  not simulated: blocked_by_preflight: the exploratory-mode preflight reports underparameterized (blocking reason missing_inputs; next action measure_or_curate_missing_inputs). The case was not simulated, so it has no samples, trajectories, metrics or threshold times; its missing inputs and measurement requests are in missing_parameters.csv and suggested_experiments.csv.

Output directory: runs/mould_b2
Manifest: runs/mould_b2/output_manifest.json
Report: runs/mould_b2/report/virtual_experiment_report.md
Limitations: 20 (4 blocking, 2 important, 14 info) in runs/mould_b2/limitations_table.csv
Provenance: 9 row(s) in runs/mould_b2/provenance_table.csv
Suggested experiments: 3 in runs/mould_b2/suggested_experiments.csv

Partial run: 1 of 2 requested case(s) were blocked by the preflight and not simulated (case_0001); exit code 4.
```

The exit code tells a script what happened:

| Exit code | Meaning | Here |
| --- | --- | --- |
| 0 | Every requested case was simulated. | After the 40 degC gap is filled ([step 6](#7-replace-estimates-with-your-own-measurements)). |
| 3 | The preflight blocks a requested case and nothing was simulated: without `--runnable-only` whenever a case is blocked, with it when no case is runnable. | The same command without `--runnable-only` (below). |
| 4 | A partial run: the runnable cases were simulated, the blocked ones are listed as `not_simulated` with their measurement requests. | The run above. |

Without `--runnable-only` the same request simulates nothing:

<!-- walkthrough-command: run-blocked -->
```bash
fungmod run --user-data mould_b2 --fungus "Synthetic fixture mould B2" \
  --substrate cellobiose --condition c30_ph5 --condition c40_ph5 \
  --mode exploratory --samples 8 --seed 1 --output runs/blocked
```

<!-- walkthrough-output: run-blocked -->
```text
...
Not runnable: 1 of 2 case(s) cannot be simulated in exploratory mode.
Nothing was simulated: FungMod simulates only when every requested case passes the preflight. Supply the missing inputs, choose other cases, or check the mode.
Add --runnable-only to simulate the 1 runnable case(s) and list the blocked one(s) as not simulated (exit code 4).
...
```

In scientific mode (`--mode scientific`, one exact run per case, no samples)
no case of this draft runs: the 30 degC kinetics are transferred estimates,
which scientific mode refuses, so the command exits with 3 even with
`--runnable-only`.

## 6. Read the outputs

The printed summary comes from the tables in `runs/mould_b2/`:

- **Degradation over time.** `time_series_long.csv` holds every state
  (cellobiose, glucose, the enzyme), the process rate and the derived
  degradation and product-release rates at each of the 61 output times of
  every sample; `trajectory_quantiles.csv` the 5th, 50th
  and 95th percentiles per time. The quick-look figures in `figures/`
  plot substrate remaining, degradation fraction, degradation rate and
  product release against time.
- **Metrics and rates.** `summary_metrics.csv` (per case and metric: count,
  mean, min, max and the 5th, 50th and 95th percentiles) and
  `final_metrics.csv` (per sample). The rates are
  `maximum_substrate_depletion_rate` (3.456 mM/h here) and
  `maximum_product_release_rate` (6.912 mM/h: two glucose per cellobiose).
- **Threshold times.** `threshold_times.csv`: the time to 10, 50 and 90 %
  substrate degradation per sample, with a `status` that says
  `not_reached` when the simulated time span is too short. They are
  interpolated linearly between output times (every 10 minutes on this
  grid), so a finer `--time-grid` resolves them more closely.
- **Uncertainty.** All 8 samples agree because every input of this case is
  an exact value. A range (`lower` and `upper` in `kinetics.csv`, or
  `--design QUANTITY=LOWER:UPPER`) is sampled in exploratory mode, and the
  percentiles then describe that stated range; they are not calibrated
  confidence intervals. `uncertainty_summary.csv` and
  `sampled_parameters.csv` say which inputs were sampled.

**Provenance.** `provenance_table.csv` gives, per case, the source, maturity
and allowed use of every record that went into it. The parameters of the
30 degC case:

<!-- walkthrough-table: provenance -->
| role | maturity | allowed_use | source |
| --- | --- | --- | --- |
| `substrate_initial_concentration` | `user_design_value` | `scientific_or_exploratory_when_all_other_inputs_are_valid` | Virtual assay design stated when drafting these tables; not reported by SABIO-RK |
| `km__beta_glucosidase__cellobiose` | `exploratory_prior` | `exploratory_simulation_only_not_literature_curated` | SABIO-RK EntryID 9900001 (FungMod test fixture) |
| `kcat__beta_glucosidase__cellobiose` | `exploratory_prior` | `exploratory_simulation_only_not_literature_curated` | SABIO-RK EntryID 9900001 (FungMod test fixture) |
| `enzyme_initial_concentration__beta_glucosidase` | `user_design_value` | `scientific_or_exploratory_when_all_other_inputs_are_valid` | Virtual assay design: an enzyme concentration chosen for this walkthrough |

The transferred Km and kcat are exploratory priors that must not be cited as
literature values for this fungus; the fungus, environment and template rows
carry the draft's sources (the proteome choice and the SABIO-RK query with
their digests).

- **Limitations.** `limitations_table.csv` has 20 rows here: 4 blocking (the
  40 degC case and its three missing inputs), 2 important (the exploratory
  priors, and what the enzyme network does not model: no competition for
  sites, no synergy, not a whole-fungus growth or secretion model) and 14
  for information. Read them before using a number.
- **Measurement requests.** `suggested_experiments.csv` and
  `missing_parameters.csv` hold the three requests of the 40 degC case,
  priority `high`; they are the experiments that would let this case run.
- **The bundle.** `case_summary.csv` lists both cases, the blocked one as
  `not_simulated` with the reason; `output_manifest.json` records the mode,
  the dataset id and digest, the partial run (`partial_run`,
  `requested_case_count` 2, `simulated_case_count` 1) and every file;
  `report/virtual_experiment_report.md` is the Markdown report (`--report`
  adds HTML and an index).

## 7. Replace estimates with your own measurements

The transferred estimates and the gap are placeholders for your own data.
When you have measured the enzyme yourself, edit `kinetics.csv`: replace the
two transferred rows of `c30_ph5` (rows 2 and 3) with your values, and add
rows for `c40_ph5`. The rows below use placeholders in angle brackets for
what you fill in; the column order is the draft's header:

<!-- walkthrough-template: own-measurements -->
```text
synthetic_fixture_mould_b2,beta_glucosidase,cellobiose,c30_ph5,km,<Km>,,,mM,measured,<how it was measured>,<where it is recorded>,<sd>,<replicates>,,,
synthetic_fixture_mould_b2,beta_glucosidase,cellobiose,c30_ph5,kcat,<kcat>,,,1/s,measured,<how it was measured>,<where it is recorded>,<sd>,<replicates>,,,
synthetic_fixture_mould_b2,beta_glucosidase,cellobiose,c40_ph5,km,<Km>,,,mM,measured,<how it was measured>,<where it is recorded>,<sd>,<replicates>,,,
synthetic_fixture_mould_b2,beta_glucosidase,cellobiose,c40_ph5,kcat,<kcat>,,,1/s,measured,<how it was measured>,<where it is recorded>,<sd>,<replicates>,,,
synthetic_fixture_mould_b2,beta_glucosidase,cellobiose,c40_ph5,enzyme_concentration,0.1,,,uM,design,experimental design,<why this amount>,,,,,
```

- `evidence_type` says what a value is: `measured` (your own measurement,
  with a `method` and a `source`), `literature` (a published value for this
  fungus), `design` (an amount of the virtual assay) or `estimate`. Keep
  `estimate` for any value that is neither your measurement nor published
  for this fungus; FungMod never upgrades it.
- `sd` and `replicates` are kept as provenance and not sampled; give `lower`
  and `upper` instead of `value` for a range that exploratory mode samples.
  Units are checked with pint. A Vmax, a specific activity with an enzyme
  loading, or a saturating assay activity can replace kcat and the enzyme
  concentration ([three rate forms](user-data.md#three-rate-forms)).
- Then `fungmod check-data mould_b2` reports no gap, and the `run` command
  of step 5 simulates both conditions (exit code 0). With `measured`,
  `literature` or `design` values in every row, `--mode scientific` runs one
  exact run per case; scientific means exact inputs and implemented
  mechanisms, not experimental validation.

You can also keep your measurements in a [user dataset](user-data.md) and
assemble with `--user-data DIR`: rows of your dataset for the fungus are case
status `user_data` and take precedence over every SABIO-RK entry. Measured
time courses can be compared with a run (`fungmod run
--compare-timecourses`) and used to fit Km with kcat or Vmax (`fungmod fit`);
see the [command line](cli.md#compare-with-your-time-courses).

## Verifying the live lookups

The UniProt search, the UniProtKB export and the SABIO-RK query were
written from the services' documentation in an environment that could not
reach them, and their tests serve synthetic responses. On a machine with
internet access, `scripts/verify_live_sources.py` (in a repository checkout)
checks them once against the live services:

```bash
python scripts/verify_live_sources.py
python scripts/verify_live_sources.py --organism "GENUS SPECIES" \
  --ec-number EC_NUMBER --substrate "SUBSTRATE NAME" --output-dir NEW_DIRECTORY
```

It sends one request to each endpoint through FungMod's own functions (the
query builders, the parsers and the snapshot checks of
`search_proteomes_by_name`, `choose_proteome`, `fetch_proteome_snapshot` and
`fetch_kinlaw_query_snapshot`, then `parse_reaction_records` and
`user_tables_from_sabiork` on the SABIO-RK answer), and prints per endpoint
the URL, the HTTP status, the headers FungMod relies on
(`X-UniProt-Release`, `X-UniProt-Release-Date`, `X-Total-Results`, the
`Link` pagination header; SABIO-RK's `meta.total_count` and
`meta.total_pages`), the columns or fields found against those expected,
the number of entries, whether FungMod's parser read the response, and
every mismatch. The defaults, *Trichoderma reesei* and EC 3.2.1.21 on
"Cellobiose" (the name of the registry's cellobiose record, which FungMod's
lookup sends), are probes of the formats only, not statements about any
fungus or enzyme; use `--proteome UP...` when the name has several
reference proteomes.

The snapshots and `verification_report.json` go to a new temporary
directory (printed and kept) or to `--output-dir`, a new or empty directory
outside the repository; nothing is written inside the repository. The exit
code is 0 when every endpoint matched, 1 on any mismatch (a response FungMod
would refuse or misread, or a documented assumption that does not hold), 2
for a usage error, and 3 when an endpoint could not be checked (no network,
a server error, a name without exactly one proteome, a query without
entries). Send the report of a mismatch to the maintainers.

The report below was produced by `tests/test_verify_live_sources.py` with
**synthetic responses** served through a patched `urlopen` (the fixtures of
this page), so it shows the report's format only, not a live result:

<!-- walkthrough-output: verify-live-sources -->
```text
FungMod live-source verification
...
  probe organism: 'Synthetic fixture mould B2' (a probe of UniProt's formats only, not a recommendation or a statement about this fungus)
  probe query: ECNumber:"3.2.1.21" AND Substrate:"Cellobiose" (a probe of SABIO-RK's format only)

[1/3] UniProt proteome search (FETCH-001: a fungus name to its reference proteome)
  FungMod: fungal_model.sources.uniprot.search_proteomes_by_name(refresh=True), choose_proteome
  query: organism_name:"Synthetic fixture mould B2" AND proteome_type:1
  URL: https://rest.uniprot.org/proteomes/search?query=organism_name:%22Synthetic%20fixture%20mould%20B2%22%20AND%20proteome_type:1&fields=upid,organism,organism_id,protein_count&format=tsv&size=500
  ok    HTTP status: 200
...
  ok    X-UniProt-Release: fixture_release
  ok    X-UniProt-Release-Date: 06-October-2026
  ok    X-Total-Results: 1, equal to the 1 row(s) of the response
  info  Link (pagination): not sent (no next page)
  info  columns expected: Proteome Id, Organism, Organism Id, Protein count
  info  columns found: Proteome Id, Organism, Organism Id, Protein count
  ok    columns: every expected column is present (compared case-insensitively)
  ok    parse_proteome_search_tsv: read 1 candidate(s)
  ok    snapshot: stored and verified in .../uniprot/organism_name_synthetic_fixture_mould_b2_32e605c891b0
...
  ok    choose_proteome: UP999990002 (Synthetic fixture mould B2 (strain FIX-2); taxonomy 9000000002; reference proteome (proteome_type:1); 5 proteins), because it is the only candidate of the search
  result: OK

[2/3] UniProtKB export of proteome UP999990002 (FETCH-001: the enzyme repertoire)
...
  info  columns expected: Entry, Entry Name, Protein names, Gene Names, Organism, Organism (ID), EC number, CAZy, Reviewed
  info  columns found: Entry, Entry Name, Protein names, Gene Names, Organism, Organism (ID), EC number, CAZy, Reviewed
  ok    columns: every expected column is present
  ok    parse_uniprot_tsv: read 5 entries
  info  EC number column: 4 of 5 entries carry a complete EC number
  info  CAZy column: 3 of 5 entries carry a CAZy family
  ok    Organism (ID): 9000000002 (Synthetic fixture mould B2 (strain FIX-2))
  ok    protein count: 5, equal to the export's entries
...
  result: OK

[3/3] SABIO-RK kinetic-law export, queried by EC number and substrate name (FETCH-002)
  FungMod: fungal_model.sources.sabiork.query_snapshots.fetch_kinlaw_query_snapshot(refresh=True)
  query: ECNumber:"3.2.1.21" AND Substrate:"Cellobiose"
  URL: https://sabio.h-its.org/export-api/sabio/kinlaw-entry/json?q=ECNumber%3A%223.2.1.21%22+AND+Substrate%3A%22Cellobiose%22&page=1&pageSize=1000
  ok    HTTP status: 200
...
  info  fields expected: meta, data, meta.total_count, meta.total_pages
  info  fields found: meta, data, meta.page, meta.page_size, meta.total_count, meta.total_pages
  ok    envelope: meta, data and meta.total_count are present
  ok    meta.total_pages: 1
...
  ok    entry fields: general, reaction, kineticlaw, enzyme_description, experimental_conditions, publication
  ok    snapshot: stored and verified in .../sabiork/ecnumber_3.2.1.21_and_substrate_cellobiose-5a9fabef44f3/... (total_count 7, 7 entries)
  ok    parse_reaction_records: read 7 entries
  ok    EC numbers: every entry states EC 3.2.1.21
  ok    organism: every entry names its organism (3 organisms)
  ok    parameters: every entry has kinetic parameters
  ok    substrate name: every entry names 'Cellobiose' as a substrate (case-insensitive)
  ok    user_tables_from_sabiork: 3 of 7 entries converted to kinetics rows; not converted: conflict (2); mutant enzyme (1); no Km, kcat or Vmax could be converted (1)
  result: OK

Summary: 3 endpoint(s): 3 OK, 0 MISMATCH, 0 NOT CHECKED; exit code 0.
...
```

A match says that the live formats are what FungMod's parsers expect; it does
not check any value, organism or enzyme. Until the script has been run
against the live services, the UniProt and SABIO-RK routes remain "not
verified live", as [from a fungus name](user-data.md#from-a-fungus-name) and
[fetching kinetics](user-data.md#fetching-kinetics) say.

## What this route does not do

- One fungus per call, dissolved substrates only, and in an enzyme network
  no temperature or pH response law yet: kinetics hold at the condition of
  their rows ([drafting an enzyme network](user-data.md#drafting-an-enzyme-network)).
- A proteome says which enzymes the fungus can encode, not which it
  expresses or secretes, or how fast; a reference proteome stands for its
  species, not your strain ([from a fungus name](user-data.md#from-a-fungus-name)).
- SABIO-RK is queried by EC number and the substrate's name only: entries
  filed under another name of the substrate are not found, and classes
  without an EC number or defined in a user dataset are not looked up
  ([fetching kinetics](user-data.md#fetching-kinetics)).
- Kinetics of another organism's enzyme are estimates for exploratory mode;
  scientific mode needs your own or same-species literature values.
- The enzyme network is independent Michaelis-Menten processes at stated
  enzyme concentrations, not a fungus growing and secreting; see
  [fungal culture](user-data.md#fungal-culture-growth-and-secretion) for the
  culture model, which assembled drafts do not carry.
