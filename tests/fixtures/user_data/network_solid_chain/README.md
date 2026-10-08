# Cross-basis enzyme-network fixture: a solid releasing a dissolved pool (NETWORK-002)

**Illustrative estimates; no measurement, literature value or registry record stands behind them.**

One user-defined strain, `strain_s3`, declares two user-defined classes. `solid_cutter_like`
acts on the suspended cellulose-like solid `solid_c3` (`solid_polymer`, `amount_basis`
`dry_mass`, substrate class `glucan_like_solid`) and releases the dissolved disaccharide-like
pool `dimer_d3`; `dimer_hydrolase_like` acts on `dimer_d3` (substrate class `dimer_like`) and
releases two monomer-like units per molecule, `monomer_m3`, the network's final product, which
competitively inhibits it. `user_dataset.yml` declares `enzyme_network: {entry_substrates: [solid_c3]}`.

The link `solid_c3 -> dimer_d3` changes basis, from a dry mass per volume to an amount per
volume. It exists only because the `substrates.csv` row of `solid_c3` states a unit-bearing
yield: `product_yield` 3.0838 with `yield_basis` `mmol/g`, `yield_evidence_type` `estimate` and a
`yield_method` saying how the user computed it (1000 / 324.28 mmol/g, from an assumed
repeat-unit molar mass of 162.14 g/mol and two units per released molecule). FungMod applies
no molar mass itself.

| Class | Pool | `km` | `kcat` | `enzyme_concentration` | `ki` |
| --- | --- | --- | --- | --- | --- |
| `solid_cutter_like` | `solid_c3` (initial 10 g/L) | 8 g/L | 0.02 g/(mg h) | 20 mg/L | none |
| `dimer_hydrolase_like` | `dimer_d3` (starts at zero) | 1.2 mM | 50 1/s | 0.00002 mM | 3 mM, `inhibitor` `monomer_m3` |

The solid is reported in g/L, `dimer_d3` and `monomer_m3` in g/L x mmol/g = mmol/L. The
closure `2 x 3.0838 mmol/g x S + 2 D + M` stays at 61.676 mmol/L. Every row is an
`estimate` (the yield too), so the case runs in exploratory mode only. The fixture is the
cross-basis case of `tests/test_user_data_network_cross_basis.py` and the worked example of
`docs/user-data.md#a-solid-releasing-a-dissolved-pool`; it tests the generic route, not a fungus.
