# Culture fixture: re-entry of the registry's T. harzianum culture case (USERDATA-009)

**A re-entry of FungMod's retrospective fit and of the deposited initial conditions; not new data.**

One strain, `strain_h1` (scientific name *Trichoderma harzianum*), declares the registry
classes `cellulase_total_filter_paper_activity` (the filter-paper activity pool, in
`filter_paper_unit`) and `beta_glucosidase` (in `beta_glucosidase_assay_unit`). It grows
on one user-defined suspended solid, `particulate_lot_h1` (`solid_polymer`, `amount_basis`
`dry_mass`, substrate class `cellulose_particulate`), at three conditions that differ only
in the cellulose loading (`load_10`, `load_20`, `load_30`: 10, 20 and 30 g/L at 29 degC,
pH 5.0). `culture.csv` gives every role of the registry culture case
`trichoderma_harzianum_cellulose_culture_template` with the values of the registry
records it binds:

| `culture.csv` quantity | Pool | Value | Evidence type | Registry record (maturity) |
| --- | --- | --- | --- | --- |
| `hydrolysis_capacity` | filter-paper activity | 0.018378579847405995 g/FPU/h | `estimate` | `gelain_hydrolysis_k_h_calibrated` (calibrated) |
| `hydrolysis_half_saturation` | filter-paper activity | 16.726013979440346 g/L | `estimate` | `gelain_hydrolysis_Kh_calibrated` (calibrated) |
| `biomass_yield` | | 0.4148331117804989 g/g | `estimate` | `gelain_hydrolysis_Y_calibrated` (calibrated) |
| `biomass_loss_rate` | | 0.019870844204703458 1/h | `estimate` | `gelain_hydrolysis_kd_calibrated` (calibrated) |
| `induction_half_saturation` | | 0.010000000000000236 g/L | `estimate` | `gelain_hydrolysis_K_ind_calibrated` (calibrated) |
| `specific_production_rate` | filter-paper activity | 5.822884641381956 FPU/g/h | `estimate` | `gelain_hydrolysis_qF_calibrated` (calibrated) |
| `enzyme_loss_rate` | filter-paper activity | 1.0000000024667456e-06 1/h | `estimate` | `gelain_hydrolysis_kF_calibrated` (calibrated) |
| `specific_production_rate` | beta-glucosidase | 13.93577774462081 BGU/g/h | `estimate` | `gelain_hydrolysis_qB_calibrated` (calibrated) |
| `enzyme_loss_rate` | beta-glucosidase | 1.0000000000000023e-06 1/h | `estimate` | `gelain_hydrolysis_kB_calibrated` (calibrated) |
| `initial_biomass` | | 0.3990672957214788 g/L | `literature` | `gelain_2020_cellulose_initial_biomass` (literature_processed) |
| `substrate_initial_concentration` | | 10, 20, 30 g/L | `literature` | `gelain_2020_cellulose_initial_loading_*gl` (literature_processed) |
| `initial_enzyme_concentration` | filter-paper activity | 0 FPU/L | `literature` | `gelain_2020_cellulose_initial_cellulase_activity` (literature_processed) |
| `initial_enzyme_concentration` | beta-glucosidase | 0 BGU/L | `literature` | `gelain_2020_cellulose_initial_beta_glucosidase_activity` (literature_processed) |

Why these evidence types: the nine constants are FungMod's own retrospective all-condition
fit of the Gelain 2020 hydrolysis candidate (registry maturity `calibrated`,
`calibrated_retrospective_unvalidated`; three of them sit at a fitting bound). They are
not values reported in the literature (the article's own constants differ), not
measurements of this strain, and not a fit of this dataset's time courses, so `literature`,
`measured` and `fitted` would each overstate them; `estimate` is the honest label and keeps
the case exploratory. The initial biomass, the initial activities and the loadings are read
directly from the deposited workbooks (registry maturity `literature_processed`), so they
are `literature`.

The substrate row's product (`solubilized_substrate_mass`, 1 g/g) is required by
`substrates.csv` and is not used by the culture form: consumed cellulose becomes biomass
at the stated yield and the rest is booked to the closure ledger, as in the registry case.
`kinetics.csv` holds only its header. The fixture exists for
`tests/test_user_data_culture.py` (parity with the registry case) and for
`docs/user-data.md#fungal-culture-growth-and-secretion`.
