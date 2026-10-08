# Enzyme-inactivation fixture: a single class that tires (USERDATA-011)

**Illustrative estimates; no measurement, literature value or registry record stands behind them.**

One user-defined strain, `strain_v1`, declares one user-defined class, `amide_hydrolase_like`
(target bond class `amide_like_bond`), which acts on the dissolved amide-like substrate
`amide_a1` (substrate class `amide_like`) and releases one amine-like product `amine_v1` per
molecule. The case is the kcat form at `c40_ph6` (40 degC, pH 6):

| `km` | `kcat` | `substrate_initial_concentration` | `enzyme_concentration` | `inactivation_rate` |
| --- | --- | --- | --- | --- |
| 4 mM | 60 1/min | 0.5 mM | 0.001 mM | 0.3 1/h |

The `inactivation_rate` row binds the existing `first_order` process law to the enzyme state:
`E(t) = E0 exp(-k_d t)`, a half-life of about 2.3 hours. Its integrated activity
`kcat E0 / k_d = 12` mM of turnover caps the conversion, so after eight hours 0.0367 mM of
substrate is left (0.000423 mM without the row). Every row is an `estimate`, so the case runs
in exploratory mode only. The fixture is the single-class case of
`tests/test_user_data_inactivation.py` and the worked example of
`docs/user-data.md#enzyme-inactivation-over-the-run`; it tests the generic route, not a fungus.
