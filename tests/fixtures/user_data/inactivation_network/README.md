# Enzyme-inactivation fixture: one member of a network loses activity (USERDATA-011)

**Illustrative estimates; no measurement, literature value or registry record stands behind them.**

One user-defined strain, `strain_w7`, declares two user-defined classes that act in parallel
on the particulate polymer-like solid `solid_w7` (substrate class `particulate_like`, a
`solid_polymer` on a dry-mass basis, 20 g/L) and release the final product `fragment_w7`
with an assumed yield of 1 g/g. `user_dataset.yml` declares
`enzyme_network: {entry_substrates: [solid_w7]}`. At `c55_ph5` (55 degC, pH 5):

| Class | `km` | `kcat` | `enzyme_concentration` | `inactivation_rate` |
| --- | --- | --- | --- | --- |
| `fast_cutter_w7` | 8 g/L | 0.05 g/(mg h) | 10 mg/L | 0.1 1/h |
| `stable_cutter_w7` | 15 g/L | 0.01 g/(mg h) | 10 mg/L | none |

`responses.csv` binds the `thermal_inactivation` law to `fast_cutter_w7` on `solid_w7`: an
activation energy of inactivation of 200 kJ/mol at the reference temperature 55 degC, where
the `inactivation_rate` is stated. The fast cutter's enzyme state therefore runs the existing
`thermal_inactivation` process law, `k_d(T) = 0.1 1/h x exp(-E_d / R (1/T - 1/T_ref))`
(0.032, 0.1 and 0.30 1/h at 50, 55 and 60 degC), and the stable cutter keeps its enzyme. No
law scales the catalytic constants. Every row is an `estimate`, so the case runs in
exploratory mode only. The fixture is the materially different case of
`tests/test_user_data_inactivation.py` (a network, a solid, protein-mass enzymes, the
Arrhenius law) and the network example of `docs/user-data.md#in-an-enzyme-network`; it tests
the generic route, not a fungus.
