# Gelain 2020 cross-solver reproduction (PEtab, COPASI)

Plan `a0f8abe9561ad1936a2ef06055cd7af8a04cf4902008790d0a14c3cb58f3184a`; outcome: **copasi_improves** (plan vocabulary).

Retrospective check that an independent simulator and optimiser reproduce FungMod's
all-condition least-squares optimum of the registry hydrolysis candidate on the same
PEtab problem. It validates no biology.

## Simulation at FungMod's optimum

- Worst |COPASI - FungMod| / sigma over all measurements: 1.65e-08 (gate 0.0001).
- Objective: COPASI 4.030662654, FungMod 4.030662656, relative difference 5.06e-10 (gate 1e-05).

| Observable | max abs difference / sigma |
| --- | --- |
| `observable_biomass` | 1.65e-08 |
| `observable_substrate` | 1.53e-08 |
| `observable_cellulase_activity` | 1.14e-08 |
| `observable_beta_glucosidase_activity` | 1.1e-08 |

## COPASI optimum

- Method: Levenberg - Marquardt, settings {"Iteration Limit": 2000, "Tolerance": 1e-06, "name": "Levenberg - Marquardt"}, integrator Deterministic (LSODA) with relative tolerance 1e-09 and absolute tolerance 1e-12.
- Local fit from FungMod's optimum: objective 3.980292263.
- Random starts: 10; objectives 3.98101, 3.97682, 3.97942, 3.98498, 3.98064, 3.97695, 3.98368, 3.97718, 4.08003, 3.98074.
- Best COPASI objective 3.976823236 (start_1) versus FungMod 4.030662656: relative difference 0.0134 (gate 0.001); COPASI improves on FungMod: yes.

| Parameter | FungMod | COPASI best | relative difference |
| --- | --- | --- | --- |
| `k_h` | 0.0126818 | 0.0180439 | 0.423 |
| `Kh` | 10.532 | 16.3302 | 0.551 |
| `Y` | 0.371701 | 0.406245 | 0.0929 |
| `kd` | 0.01792 | 0.0192504 | 0.0742 |
| `K_ind` | 0.0100876 | 0.01 | 0.00868 |
| `qF` | 6.88366 | 5.91219 | 0.141 |
| `kF` | 3.90392e-05 | 1.00001e-06 | 0.974 |
| `qB` | 15.9925 | 14.138 | 0.116 |
| `kB` | 1.24274e-06 | 1e-06 | 0.195 |

Parameter differences are reported, not gated: stage A of the criticism study found two
weakly determined directions along which equally good optima differ.

At COPASI's best point FungMod's compiled core gives objective 3.976823208 against COPASI's 3.976823236 (relative difference 7.19e-09); reported, not gated.

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
