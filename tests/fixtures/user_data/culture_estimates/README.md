# Culture fixture: illustrative estimates on a xylan-like solid (USERDATA-009)

**Illustrative estimates; no measurement, literature value or registry record stands behind them.**

One user-defined strain, `strain_x1`, with one user-defined class, `endo_xylanase_like`
(EC 3.2.1.8 names the activity; target bond class `beta_1_4_xylosidic`, compatible
substrate class `xylan_like_solid`), grows on one user-defined suspended solid,
`xylan_lot_x1` (`solid_polymer`, `amount_basis` `dry_mass`), at one condition (`c25`,
25 degC, pH 6.0). The culture has one induced enzyme pool stated as a protein mass
(mg/L), so `hydrolysis_capacity` is g/(mg h) and `specific_production_rate` mg/(g h):

| `culture.csv` quantity | Value |
| --- | --- |
| `substrate_initial_concentration` | 15 g/L |
| `initial_biomass` | 0.2 g/L |
| `biomass_yield` | 0.35 g/g |
| `biomass_loss_rate` | 0.01 1/h |
| `induction_half_saturation` | 0.5 g/L |
| `hydrolysis_capacity` | 0.005 g/mg/h |
| `hydrolysis_half_saturation` | 5 g/L |
| `initial_enzyme_concentration` | 1 mg/L |
| `specific_production_rate` | 5 mg/g/h |
| `enzyme_loss_rate` | 0.02 1/h |

Every row is an `estimate`, so the case runs in exploratory mode only and scientific mode
refuses it. The substrate row's product (`solubilized_substrate_mass`, 1 g/g) is required by
`substrates.csv` and is not used by the culture form. The fixture is the materially
different, non-cellulose case of `tests/test_user_data_culture.py` and the worked example of
`docs/user-data.md#fungal-culture-growth-and-secretion`; it tests the generic route, not a
fungus.
