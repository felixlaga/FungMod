# Enzyme-network fixture with response laws (NETWORK-003)

**Illustrative estimates; no measurement, literature value or registry record stands behind them.**

The pools, classes, links and kinetics are those of the `network_chain` fixture: one
user-defined strain, `strain_n1`, whose class `depolymerase_like` cuts the soluble
polymer-like substrate `polymer_p1` into four oligomer-like units (`oligomer_o1`) and whose
class `oligomer_hydrolase_like` cuts each oligomer-like unit into two monomer-like units
(`monomer_m1`, the final product). `responses.csv` adds a temperature and a pH law to the
first process and a temperature law to the second:

| Class on pool | Law | Parameters | Reference |
| --- | --- | --- | --- |
| `depolymerase_like` on `polymer_p1` | `temperature_cardinal_rosso` | T_min 5, T_opt 30, T_max 45 degC | T_opt 30 degC |
| `depolymerase_like` on `polymer_p1` | `ph_cardinal_rosso` | pH_min 3, pH_opt 5, pH_max 8 | pH_opt 5 |
| `oligomer_hydrolase_like` on `oligomer_o1` | `temperature_arrhenius_reference` | E_a 50 kJ/mol, T_ref 30 degC | T_ref 30 degC |

The kinetics rows are stated at `c30_ph5` (30 degC, pH 5), the reference condition of every
law, so they are reference values. Each law scales only the rate of its own process; at an
`EnvironmentGrid` condition (for example `--temperature-c 37 --ph 5.5`) the first process runs
at `kcat E S / (Km + S) x gamma_T(T) x gamma_pH(pH)` and the second at
`kcat E S / (Km + S) x exp(-E_a / R (1/T - 1/T_ref))`. Every value is an `estimate`, so the case
runs in exploratory mode only. The fixture is the non-specific network-with-laws case of
`tests/test_user_data_network_responses.py` and the worked example of
`docs/user-data.md#response-laws-in-a-network`; it tests the generic route, not a fungus.
