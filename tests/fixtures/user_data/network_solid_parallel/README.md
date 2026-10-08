# Cross-basis enzyme-network fixture: two classes on a solid releasing a molar product (NETWORK-002)

**Illustrative estimates; no measurement, literature value or registry record stands behind them.**

One user-defined strain, `strain_r4`, declares two user-defined classes that both act on the
suspended chitin-like solid `solid_k4` (`solid_polymer`, `amount_basis` `dry_mass`, substrate
class `aminoglycan_like_solid`) and release a dissolved dimer-like product, `dimer_k4`, which is
no substrate of the dataset and so the network's final product. `user_dataset.yml` declares
`enzyme_network: {entry_substrates: [solid_k4]}`.

The release changes basis through the unit-bearing yield of the `solid_k4` row: `product_yield`
2460.6 with `yield_basis` `umol/g`, `yield_evidence_type` `estimate`, computed by the user as
1e6 / 406.4 umol/g from an assumed repeat-unit molar mass of 203.2 g/mol and two units per
released molecule. The product is therefore reported in g/L x umol/g = umol/L.

| Class | Form | Constants |
| --- | --- | --- |
| `endo_cutter_like` | kcat | `km` 20 g/L, `kcat` 0.004 g/(mg h), `enzyme_concentration` 25 mg/L |
| `exo_cutter_like` | Vmax | `km` 40 g/L, `vmax` 0.05 g/L/h |

Both classes state the same initial solid, 2 g/L. Every row is an `estimate`, so the case runs
in exploratory mode only. It is the materially different cross-basis case of
`tests/test_user_data_network_cross_basis.py`: other units (umol/g, a product in umol/L), two
classes in parallel in two rate forms, and a basis change into the final product rather than
into an intermediate pool.
