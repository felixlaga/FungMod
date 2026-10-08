# Enzyme-network fixture: a chain of pools (USERDATA-010)

**Illustrative estimates; no measurement, literature value or registry record stands behind them.**

One user-defined strain, `strain_n1`, declares two user-defined classes. `depolymerase_like`
acts on the soluble polymer-like substrate `polymer_p1` (substrate class `soluble_polymer_like`)
and releases four oligomer-like units per molecule; `oligomer_hydrolase_like` acts on the
oligomer-like pool `oligomer_o1` (substrate class `oligomer_like`) and releases two
monomer-like units per molecule. The link `polymer_p1 -> oligomer_o1` exists only because the
`substrates.csv` product of `polymer_p1` is the `substrate_id` `oligomer_o1`; `monomer_m1` is no
substrate of the dataset, so it is the network's final product. `user_dataset.yml` declares
`enzyme_network: {entry_substrates: [polymer_p1]}`.

| Class | Pool | `km` | `kcat` | `enzyme_concentration` |
| --- | --- | --- | --- | --- |
| `depolymerase_like` | `polymer_p1` (initial 5 mM) | 2 mM | 30 1/min | 0.002 mM |
| `oligomer_hydrolase_like` | `oligomer_o1` (starts at zero) | 1 mM | 60 1/min | 0.001 mM |

Every row is an `estimate`, so the case runs in exploratory mode only. The closure
`8 P + 2 O + M` (weights from the yields 4 and 2 mol/mol) stays at 40 mM. The fixture is the
non-specific network case of `tests/test_user_data_network.py` and the worked example of
`docs/user-data.md#several-enzymes-acting-together`; it tests the generic route, not a fungus.
