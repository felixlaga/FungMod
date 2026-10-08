# Culture fixture: two strains sharing two consuming pools on a chitin-like solid (CULTURE-002)

**Illustrative estimates; no measurement, literature value or registry record stands behind them.**

Two user-defined strains, `strain_k6` and `strain_k7`, grow on one user-defined suspended solid,
`solid_k6` (`solid_polymer`, `amount_basis` `dry_mass`, substrate class
`aminoglycan_like_solid`), and both secrete the user-defined pools `endo_cleaver_k_like` and
`exo_cleaver_k_like` (protein masses, mg/L), which both act on the solid and consume it in
parallel. The two strains share one culture model, named by the first consuming pool of the
first culture in `culture.csv` (`endo_cleaver_k_like`), although `strain_k7` lists its pools in
the other order.

- `strain_k6` at `c30_ph6` (30 degC, pH 6.0): 8 g/L solid, 0.1 g/L biomass, yield 0.3 g/g, loss
  0.01 1/h, induction half-saturation 0.5 g/L; `endo_cleaver_k_like` k_h 0.003 g/(mg h), K_h 4 g/L,
  0.4 mg/L, 2 mg/(g h), 0.02 1/h; `exo_cleaver_k_like` k_h 0.002 g/(mg h), K_h 2 g/L, 0.6 mg/L,
  1 mg/(g h), 0.03 1/h.
- `strain_k7` at `c30_ph6`: the same, except a yield of 0.25 g/g and the consumption capacities as
  ranges (0.002 to 0.004 and 0.0015 to 0.0025 g/(mg h)), which exploratory mode samples.
- `c37_ph6` has no rows: every role of both strains is an explicit gap with a measurement request.

Every row is an `estimate`. The fixture is the materially different case of
`tests/test_user_data_culture_pools.py`; it tests the generic route, not a fungus.
