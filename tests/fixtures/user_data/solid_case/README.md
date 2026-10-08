# Solid-substrate fixture (USERDATA-008)

**Re-entered registry constants with design loadings; not a measurement.**

One strain with the registry enzyme class `cellulase_total_filter_paper_activity`
(an assay-defined filter-paper activity pool, in `filter_paper_unit`) on one
user-defined suspended solid, `particulate_lot_p1` (`physical_state`
`solid_polymer`, `amount_basis` `dry_mass`, substrate class
`cellulose_particulate`). The product is a mass-equivalent pool of solubilized
substrate with a stated yield of 1 g per g dry substrate consumed; no product
identity is claimed.

| Row content | Value | Evidence type | Origin |
| --- | --- | --- | --- |
| `km` | 16.726013979440346 g/L | `estimate` | FungMod registry record `gelain_hydrolysis_Kh_calibrated`, a retrospective fit (T. harzianum P49P11 on Celufloc 200) |
| `kcat` | 0.018378579847405995 g/FPU/h | `estimate` | FungMod registry record `gelain_hydrolysis_k_h_calibrated`, the same fit |
| `substrate_initial_concentration` | 20 g/L | `design` | virtual assay design |
| `enzyme_dose` | 5 FPU/g (`dose_5`), 1.25 FPU/g (`dose_1_25`) | `design` | virtual assay design; enzyme concentration 100 and 25 FPU/L |
| `reactivity_exponent` | 1 | `estimate` | the linear substrate reactivity factor of Kadam et al. (2004), assumed, not measured |

The constants are typed in as estimates because they are a fit, not a
measurement of this strain or lot, so the case runs in exploratory mode only.
The two conditions share temperature and pH and differ in the enzyme dose. It
exists for `tests/test_user_data_solid_substrates.py` and the worked example
of `docs/user-data.md#solid-substrates`.
