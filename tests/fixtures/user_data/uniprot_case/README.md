# UniProt-route format fixture (USERDATA-007)

**Format fixture; synthetic accessions; not a real proteome.**

`annotations/strain_u1_uniprot.tsv` was written by hand in the column format of
a UniProtKB TSV export (tab-separated; `Entry`, `Entry Name`, `Protein names`,
`Gene Names`, `Organism`, `Organism (ID)`, `EC number`, `CAZy`, `Reviewed`,
plus an extra `Length` column that the reader ignores). Nothing was
downloaded from UniProt and no organism stands behind it: the accessions
`X0TEST01` to `X0TEST12`, the entry names, protein names, gene names and
lengths are invented, the organism is called "Synthetic format-fixture
organism" with taxonomy id `0` (not an NCBI taxon), and the proteome
identifier `UP000000000` named in `genomes.csv` stands in for a real one. The
`annotation_tool` and `source` cells of `genomes.csv` say so. It exists to
exercise the UniProt rows of `genomes.csv` in `tests/test_user_data_uniprot.py`.

The rows reach every branch of the route with the shipped registry, whose
enzyme classes with an EC number are `beta_glucosidase` (EC 3.2.1.21) and,
since USERDATA-008, `cellobiohydrolase` (EC 3.2.1.91, alias 3.2.1.176):

| Accession | EC number | CAZy | Outcome with the shipped registry |
| --- | --- | --- | --- |
| `X0TEST01` | 3.2.1.21 | GH3 | beta_glucosidase, CAZy and EC agree (reviewed) |
| `X0TEST02` | | GH1 | beta_glucosidase from CAZy only |
| `X0TEST03` | 3.2.1.21 | | beta_glucosidase from EC only |
| `X0TEST04` | 3.2.1.21 | CBM1, GH7 | disagreement (GH7: cellobiohydrolase; EC: beta_glucosidase; both contested); supports no class |
| `X0TEST05` | 3.2.1.91 | CBM1, GH7 | cellobiohydrolase, CAZy and EC agree (reviewed); a gap only on a solid cellulose substrate, which this fixture does not have |
| `X0TEST06` | 3.2.1.4 | GH5 | cellulase_generic from CAZy; 3.2.1.4 unresolved and not comparable |
| `X0TEST07` | 3.2.1.- | | partial EC number, never resolved |
| `X0TEST08` | | GT2 | unmapped family |
| `X0TEST09` | 3.2.1.3 | GH15 | glucoamylase from CAZy (no record: unmodellable); 3.2.1.3 unresolved |
| `X0TEST10` | 3.2.1.37 | GH3 | disagreement (GH3: beta_glucosidase, whose registry EC is 3.2.1.21); supports no class |
| `X0TEST11` | 3.1.1.73; 3.2.1.- | | unknown EC number (unresolved) and a partial one |
| `X0TEST12` | | | no evidence |

CBM1 is unmapped. The substrates are the registry substrate `cellobiose` and
a user-defined dissolved `maltose`; the tests add a test-only glucoamylase
class with EC 3.2.1.3 to an in-memory copy of the registry, under which
`X0TEST09` has agreeing CAZy and EC evidence for a class on that non-cellulose
substrate. `enzymes.csv` holds its header only and `kinetics.csv` no values:
every class comes from the export and every role is a gap.
