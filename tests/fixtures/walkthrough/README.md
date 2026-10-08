# Frozen snapshots of synthetic responses for the walkthrough (DOCS-WALK-001)

**Synthetic test responses written by hand; not UniProt or SABIO-RK data. No
organism stands behind any row or entry, and no value is a measurement.**

`docs/walkthrough.md` runs `fungmod assemble --fetch-proteome --fetch-kinetics
--network` offline with `--snapshot-dir tests/fixtures/walkthrough/uniprot` and
`--cache-dir tests/fixtures/walkthrough/sabiork`, and
`tests/test_walkthrough_doc.py` reruns every command shown there against these
snapshots. They are FungMod's own snapshot layouts (digest-checked on every
read), made on 2026-10-08 by running that command once with `--fetch` while
`urllib.request.urlopen` and the SABIO-RK fetch module's `urlopen` were patched
to serve the existing synthetic fixtures (the tests' `_FakeUniprot` and
`_FakeSabio`); nothing was downloaded. Their raw response files are those
fixtures byte for byte, which the test checks:

| Snapshot | Raw response file | Same bytes as |
| --- | --- | --- |
| `uniprot/organism_name_synthetic_fixture_mould_b2_32e605c891b0/` | `proteomes.tsv` | `tests/fixtures/uniprot_proteome_search/search_fixture_mould_b2.tsv` |
| `uniprot/proteome_UP999990002/` | `uniprotkb.tsv` | `tests/fixtures/uniprot_proteome_search/proteome_UP999990002_uniprotkb.tsv` |
| `sabiork/ecnumber_3.2.1.21_and_substrate_cellobiose-5a9fabef44f3/<snapshot id>/` | `raw/page_0001.json` | `tests/fixtures/sabiork_kinetics_queries/ecnumber_3_2_1_21_cellobiose.json` |

The `snapshot.json` and `fetch_metadata.json` files record the retrieval time
of that run and the release header the fake served (`fixture_release`), not a
UniProt release. See the READMEs of the two source fixture directories for
what each synthetic row and entry stands for. The files are byte-compared
(SHA-256), so `.gitattributes` marks this directory `-text`.
