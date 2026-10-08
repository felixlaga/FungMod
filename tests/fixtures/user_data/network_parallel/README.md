# Enzyme-network fixture: two classes in parallel with product inhibition (USERDATA-010)

**Illustrative estimates; no measurement, literature value or registry record stands behind them.**

One user-defined strain, `strain_q2`, declares two user-defined classes that both act on one
user-defined dissolved ester-like substrate, `ester_s2`, and release one acid-like product,
`acid_a2`, per molecule (no substrate of the dataset, so the network's final product).
`user_dataset.yml` declares `enzyme_network: {entry_substrates: [ester_s2]}`.

| Class | Form | Constants | Inhibition |
| --- | --- | --- | --- |
| `cleaver_a_like` | kcat | `km` 400 uM, `kcat` 2 1/min, `enzyme_concentration` 0.5 uM | `ki` 200 uM, `inhibitor` `acid_a2` |
| `cleaver_b_like` | Vmax | `km` 50 uM, `vmax` 0.5 uM/min | none (no `ki` row) |

Both classes state the same initial substrate concentration, 1000 uM, as they must: they act
on one pool. Every row is an `estimate`, so the case runs in exploratory mode only. The fixture
is the materially different network case of `tests/test_user_data_network.py`: two classes in
parallel, two rate forms and a competitive product-inhibition constant.
