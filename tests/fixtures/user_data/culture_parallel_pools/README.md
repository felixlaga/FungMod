# Culture fixture: two pools consuming a cellulose-like solid in parallel (CULTURE-002)

**Illustrative estimates; no measurement, literature value or registry record stands behind them.**

One user-defined strain, `strain_g5`, grows on one user-defined suspended solid, `solid_g5`
(`solid_polymer`, `amount_basis` `dry_mass`, substrate class `glucan_like_solid`), at one
condition (`c28_ph5`, 28 degC, pH 5.0), and secretes three user-defined enzyme pools stated as
protein masses (mg/L). `endo_cutter_g5_like` and `exo_cutter_g5_like` both act on the solid (bond
class `glycosidic_like_bond`), so both consume it, each by its own
`k_h E S / (K_h + S)`; their rates add and every consumed gram feeds growth through the one
yield. `dimer_hydrolase_g5_like` acts on no substrate of the dataset, so it is produced and lost
only.

| `culture.csv` quantity | Culture | `endo_cutter_g5_like` | `exo_cutter_g5_like` | `dimer_hydrolase_g5_like` |
| --- | --- | --- | --- | --- |
| `substrate_initial_concentration` | 12 g/L | | | |
| `initial_biomass` | 0.15 g/L | | | |
| `biomass_yield` | 0.4 g/g | | | |
| `biomass_loss_rate` | 0.005 1/h | | | |
| `induction_half_saturation` | 0.8 g/L | | | |
| `hydrolysis_capacity` | | 0.004 g/(mg h) | 0.006 g/(mg h) | |
| `hydrolysis_half_saturation` | | 6 g/L | 10 g/L | |
| `initial_enzyme_concentration` | | 0.5 mg/L | 0.3 mg/L | 0.2 mg/L |
| `specific_production_rate` | | 1.5 mg/(g h) | 1 mg/(g h) | 0.3 mg/(g h) |
| `enzyme_loss_rate` | | 0.015 1/h | 0.01 1/h | 0.02 1/h |

Every row is an `estimate`, so the case runs in exploratory mode only and scientific mode
refuses it. The substrate row's product is required by `substrates.csv` and is not used by the
culture form. The fixture is the non-specific case of `tests/test_user_data_culture_pools.py` and
the worked example of `docs/user-data.md#several-pools-consuming-the-substrate`; it tests the
generic route, not a fungus.
