# Synthetic UniProt responses for the fetch-by-name tests (FETCH-001)

**Synthetic test responses written by hand; not UniProt data. Nothing here was
downloaded from UniProt, and no organism stands behind any row.**

The files stand in for the bodies UniProt's REST API returns, in the format its
documentation describes, so that `tests/test_fetch_by_name.py` can exercise
`fungal_model.sources.uniprot` (organism name -> reference proteome ->
UniProtKB export) and `fungmod assemble --fetch-proteome` with
`urllib.request.urlopen` patched. The tests never reach the network; the
format and column names were not checked against a live response, because the
environment the tests were written in could not reach rest.uniprot.org.

| File | Stands in for | Rows |
| --- | --- | --- |
| `search_format_fixture_organism.tsv` | `GET /proteomes/search?query=organism_name:"Synthetic format-fixture organism" AND proteome_type:1&fields=upid,organism,organism_id,protein_count&format=tsv&size=500` | `UP000000000` named exactly like the search (chosen by the exact-name rule) and `UP999990001`, a strain of it (not chosen) |
| `search_fixture_mould_b2.tsv` | the same search for `Synthetic fixture mould B2` | one candidate, `UP999990002`, whose organism name adds a strain (chosen as the only candidate) |
| `search_fixture_mould.tsv` | the same search for `Synthetic fixture mould` | two candidates, none named exactly that (refused as ambiguous) |
| `search_no_candidate.tsv` | a search with a header and no row | none (refused) |
| `proteome_UP999990002_uniprotkb.tsv` | `GET /uniprotkb/stream?query=(proteome:UP999990002)&fields=accession,id,protein_name,gene_names,organism_name,organism_id,ec,xref_cazy,reviewed&format=tsv` | five entries of the second organism |

The proteome export of `UP000000000` is the existing format fixture
`tests/fixtures/user_data/uniprot_case/annotations/strain_u1_uniprot.tsv`
(organism "Synthetic format-fixture organism", taxonomy id `0`).

Everything is invented: the organism names; the proteome identifiers
`UP999990001` to `UP999990003` (placeholders far above the identifiers UniProt
has issued so far; `UP000000000` is the repository's existing placeholder);
the taxonomy ids `9000000001` to `9000000003` (placeholders far above the NCBI
taxonomy ids issued so far; `0` is not an NCBI taxon); the protein counts; and
the accessions `X9B2P001` to `X9B2P005` with their entry, protein and gene
names. The column headers are the ones UniProt documents (`Proteome Id`,
`Organism`, `Organism Id`, `Protein count` for proteomes; `Entry`,
`Entry Name`, `Protein names`, `Gene Names`, `Organism`, `Organism (ID)`,
`EC number`, `CAZy`, `Reviewed` for UniProtKB).

Outcomes of `proteome_UP999990002_uniprotkb.tsv` with the shipped registry:

| Accession | EC number | CAZy | Outcome |
| --- | --- | --- | --- |
| `X9B2P001` | 3.2.1.21 | | beta_glucosidase from EC only |
| `X9B2P002` | 3.2.1.8 | GH11 | endo_xylanase, CAZy and EC agree (reviewed) |
| `X9B2P003` | 3.2.1.14 | CBM18, GH18 | chitinase, CAZy and EC agree; CBM18 unmapped |
| `X9B2P004` | | AA9 | lytic_polysaccharide_monooxygenase (no registry record: unmodellable) |
| `X9B2P005` | 3.1.1.1 | | unresolved EC number |

No file carries a rate, a kinetic constant or an expression level; the
proteome route never reads one.
