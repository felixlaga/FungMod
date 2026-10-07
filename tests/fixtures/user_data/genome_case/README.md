# Genome-route format fixture (USERDATA-003)

**Format fixture: synthetic gene identifiers; not a real genome.**

`annotations/strain_g1_overview.txt` was written by hand in the documented
dbCAN3 `overview.txt` format (tab-separated; `Gene ID`, `EC#`, the tool
columns `HMMER`, `dbCAN_sub` and `DIAMOND`, and `#ofTools`). No dbCAN run,
no assembly and no organism stands behind it; the gene identifiers
`synthetic_g001` to `synthetic_g010` are invented, and `genomes.csv` says so
in its `annotation_tool` and `source` cells. It exists to exercise the
`genomes.csv` route of `load_user_dataset` in `tests/test_user_data_genome.py`.

The families are chosen to reach every branch of the route with the shipped
registry and CAZy family map:

| Gene | Calls | Family map | Shipped registry |
| --- | --- | --- | --- |
| `synthetic_g001` | GH3 by three tools | beta_glucosidase (polyspecific) | record exists |
| `synthetic_g002` | GH1 by two tools | beta_glucosidase (polyspecific) | record exists |
| `synthetic_g003` | GH3 by DIAMOND only | beta_glucosidase (polyspecific) | record exists |
| `synthetic_g004` | GH7 | cellobiohydrolase | record exists since USERDATA-008 (acts on solid cellulose classes only, so no case on these substrates) |
| `synthetic_g005` | GH10 | endo_xylanase | record exists since REGISTRY-002 (acts on registry xylan only, so no case on these substrates) |
| `synthetic_g006` | AA1 (subfamily AA1_1) | laccase | no record |
| `synthetic_g007` | GH5 by HMMER only, CBM1 by two tools | GH5: cellulase_generic; CBM1: unmapped | record exists (GH5) |
| `synthetic_g008` | GT2 | unmapped | |
| `synthetic_g009` | GH15 | glucoamylase | record exists since REGISTRY-002 (acts on registry starch only, so no case on these substrates) |
| `synthetic_g010` | none | | |

The substrates are the registry substrate `cellobiose` (compatible with the
registry class `beta_glucosidase`) and a user-defined dissolved `maltose`,
which no shipped registry class acts on; the tests widen the shipped
glucoamylase record (solid starch only) to the `maltose` class in an in-memory
copy of the registry to exercise a resolved class on that dissolved
non-cellulose substrate. `laccase` (AA1) is the class without a registry
record. `enzymes.csv` holds its header only and
`kinetics.csv` no values: every class comes from the annotation and every role
is a gap.
