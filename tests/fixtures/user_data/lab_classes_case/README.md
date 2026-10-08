# Enzyme classes a lab defines itself, with EC numbers (FETCH-003)

**Illustrative estimates; no measurement, literature value or registry record stands behind them.**

One user-defined strain, `strain_k6` ("Lab strain K6", scientific name `Synthetic kinetics
organism K6`, the synthetic organism of the FETCH-003 SABIO-RK test responses), declares two
classes that the registry does not have and that `enzyme_classes.csv` defines with an EC number:

| Class | `ec_number` | Acts on (substrate class, bond class) | Substrate of this dataset |
| --- | --- | --- | --- |
| `lab_ester_hydrolase` | 3.1.1.1 | `aryl_ester`, `carboxylic_ester` | `pnp_butyrate` ("4-Nitrophenyl butyrate") |
| `lab_phosphomonoesterase` | 3.1.3.2 | `aryl_phosphate`, `phosphoric_monoester` | `pnp_phosphate` ("4-Nitrophenyl phosphate") |

Both substrates release `p_nitrophenol`, one mole per mole. `kinetics.csv` holds the lab's own
rows for `lab_ester_hydrolase` on `pnp_butyrate` at `c25_ph7` (Km 0.4 mM, kcat 25 1/s,
substrate 1 mM, enzyme 0.05 uM, all `estimate`); `lab_phosphomonoesterase` has no kinetics.

The fixture is the user dataset of `tests/test_fetch_kinetics_user_classes.py`: with
`assemble_user_tables(fetch_kinetics=True)` (`fungmod assemble --fetch-kinetics`) each class is
looked up in SABIO-RK by its own `ec_number` and the substrate's name, and the synthetic
responses in `tests/fixtures/sabiork_kinetics_queries/` (not SABIO-RK data) give
`lab_ester_hydrolase` same-species literature kinetics at 30 degC, pH 7 and a transferred
estimate at 37 degC, pH 7.5, and `lab_phosphomonoesterase` a Vmax-form transfer at 40 degC,
pH 5. It tests the generic route, not a fungus.
