# Gelain 2020 cross-solver reproduction (PEtab, COPASI)

Plan `cfb8c9a651240081b3bcd7a0b82a7c2fc3853c1b3d9f2d01218eff23fff64628`; outcome: **reproduced** (plan vocabulary).

Retrospective check that an independent simulator and optimiser reproduce FungMod's
all-condition least-squares optimum of the registry hydrolysis candidate on the same
PEtab problem. It validates no biology.

## Simulation at FungMod's optimum

- Worst |COPASI - FungMod| / sigma over all measurements: 1.64e-08 (gate 0.0001).
- Objective: COPASI 3.976071981, FungMod 3.976071899, relative difference 2.07e-08 (gate 1e-05).

| Observable | max abs difference / sigma |
| --- | --- |
| `observable_biomass` | 1.33e-08 |
| `observable_substrate` | 1.3e-08 |
| `observable_cellulase_activity` | 1.64e-08 |
| `observable_beta_glucosidase_activity` | 1.62e-08 |

## COPASI optimum

- Method: Levenberg - Marquardt, settings {"Iteration Limit": 2000, "Tolerance": 1e-06, "name": "Levenberg - Marquardt"}, integrator Deterministic (LSODA) with relative tolerance 1e-09 and absolute tolerance 1e-12.
- Local fit from FungMod's optimum: objective 3.976071799.
- Random starts: 10; objectives 3.98101, 3.97682, 3.97942, 3.98498, 3.98064, 3.97695, 3.98368, 3.97718, 4.08003, 3.98074.
- Best COPASI objective 3.976071799 (local_fit) versus FungMod 3.976071899: relative difference 2.51e-08 (gate 0.001); COPASI improves on FungMod: no.

| Parameter | FungMod | COPASI best | relative difference |
| --- | --- | --- | --- |
| `k_h` | 0.0183939 | 0.0183948 | 5e-05 |
| `Kh` | 16.7454 | 16.7442 | 7.38e-05 |
| `Y` | 0.4146 | 0.414592 | 1.9e-05 |
| `kd` | 0.0198481 | 0.019849 | 4.68e-05 |
| `K_ind` | 0.01 | 0.01 | 1.11e-14 |
| `qF` | 5.8233 | 5.82329 | 1.33e-06 |
| `kF` | 1e-06 | 1e-06 | 6.33e-07 |
| `qB` | 13.9378 | 13.9372 | 4.1e-05 |
| `kB` | 1e-06 | 1e-06 | 4.23e-11 |

Parameter differences are reported, not gated: stage A of the criticism study found two
weakly determined directions along which equally good optima differ.

At COPASI's best point FungMod's compiled core gives objective 3.976071724 against COPASI's 3.976071799 (relative difference 1.89e-08); reported, not gated.

## Weights

COPASI's PEtab importer stored each observable's sigma as the column weight; the runner
rewrote every weight to 1/sigma^2 and switched off per-experiment normalisation:

| Condition | Observable | sigma | importer weight | weight used |
| --- | --- | --- | --- | --- |
| `gelain_2020_cellulose_10gl` | `observable_biomass` | 9.40626 | 9.40626 | 0.0113023 |
| `gelain_2020_cellulose_10gl` | `observable_substrate` | 31.1884 | 31.1884 | 0.00102805 |
| `gelain_2020_cellulose_10gl` | `observable_cellulase_activity` | 887.643 | 887.643 | 1.26918e-06 |
| `gelain_2020_cellulose_10gl` | `observable_beta_glucosidase_activity` | 2150.8 | 2150.8 | 2.16173e-07 |
| `gelain_2020_cellulose_20gl` | `observable_biomass` | 9.40626 | 9.40626 | 0.0113023 |
| `gelain_2020_cellulose_20gl` | `observable_substrate` | 31.1884 | 31.1884 | 0.00102805 |
| `gelain_2020_cellulose_20gl` | `observable_cellulase_activity` | 887.643 | 887.643 | 1.26918e-06 |
| `gelain_2020_cellulose_20gl` | `observable_beta_glucosidase_activity` | 2150.8 | 2150.8 | 2.16173e-07 |
| `gelain_2020_cellulose_30gl` | `observable_biomass` | 9.40626 | 9.40626 | 0.0113023 |
| `gelain_2020_cellulose_30gl` | `observable_substrate` | 31.1884 | 31.1884 | 0.00102805 |
| `gelain_2020_cellulose_30gl` | `observable_cellulase_activity` | 887.643 | 887.643 | 1.26918e-06 |
| `gelain_2020_cellulose_30gl` | `observable_beta_glucosidase_activity` | 2150.8 | 2150.8 | 2.16173e-07 |

## Versions

copasi 4.48.309+ (Source), basico 0.87, copasi_petab_importer 1.0.9.

## What this does not show

- biological validation
- blind or independent prediction
- that the optimum is unique or the parameters identified (see the criticism and Bayesian studies)
- any statement about models other than M0_baseline
