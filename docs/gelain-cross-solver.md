# Gelain 2020 cross-solver reproduction (PEtab, COPASI)

A retrospective check that an independent simulator and optimiser reproduce
FungMod's all-condition least-squares optimum of the registry hydrolysis
candidate (`trichoderma_harzianum_p49p11` x `cellulose_celufloc_200`) on the
three Gelain 2020 cellulose loadings, when both work on the same
[PEtab](standards.md#petab-parameter-estimation) problem. It is step 5 item 4
of the software-paper plan. It validates no biology: the data already informed
the fit being reproduced, and the check says only that two solvers agree on
this problem.

## The frozen plan

`data/benchmarks/gelain_2020_petab/plan.json` (SHA-256
`11dfe15850b80c3217dd821547613365cb77c88d39a007f65cd954ae1706d320`,
pinned by `tests/test_gelain_petab.py`) fixes, before any COPASI run: the
sources and their digests (the criticism plan, the Bayesian plan, the
observations and the stage A `M0_baseline` primary fit that is FungMod's
optimum), the objective, the COPASI settings (importer, weight correction,
LSODA at relative tolerance 1e-9 and absolute tolerance 1e-12,
Levenberg-Marquardt, one local fit from FungMod's optimum and ten log-uniform
random starts with seed 20261005), two gates and three outcomes. A first
dated amendment (`a0f8abe9...` to `cfb8c9a6...`) replaced the reference-fit
digest after the criticism plan's amendment 3 re-ran stage A with a declared
finite-difference step; the first run under `a0f8abe9...` is described below
because it is what found the defect. A second (`cfb8c9a6...` to the current
digest, 2026-10-06) re-pinned the criticism plan after its amendment 4, which
changed only the stage B posterior section; the sections this study reads
(models, data, shared structure, stage A) are unchanged, so the amendment
records `results_remain_valid` and the results recorded under `cfb8c9a6...`
stand.

| Gate | Threshold |
| --- | --- |
| Simulation agreement at FungMod's optimum | max abs difference / sigma ≤ 1e-4 at every measurement; objectives within 1e-5 |
| Optimum agreement | COPASI's best objective within 0.1 percent of FungMod's |

Outcomes: `reproduced` (both gates pass), `copasi_improves` (COPASI finds an
objective lower than FungMod's by more than the tolerance, reported as a
FungMod optimiser shortfall), `not_reproduced` (anything else). Parameter
differences are reported, not gated, because stage A of the
[criticism study](gelain-model-criticism.md) found two weakly determined
directions along which equally good optima differ.

## The problem

`fungal_model.research.gelain_petab.build_problem` materialises the registry
case at the three loadings with the stage A fitted values, assembles each
condition, and calls `conditions_to_petab`. The export needed three additions
to the SBML writer, all generic and tested on non-Gelain cases: the
`proportional_synthesis` process, parameter-bound stoichiometric coefficients
(the yield `Y` and its complement, written as separate reactions whose kinetic
laws multiply the hydrolysis rate by `Y` and `1 - Y`), and assay-activity
units written as named dimensionless unit definitions. The problem has one
SBML model, three conditions (the cellulose loading as a species column and
the matching initial-loading parameter), four observables, 96 measurements
with sigma equal to each observable's maximum over the loadings (the stage A
`primary` normalisation), and the nine registry symbols with the criticism
plan's bounds on a log10 scale.

Before any COPASI call, FungMod's own objective on the exported problem equals
twice the recorded stage A cost (`3.976071899`, relative difference below
1e-9 on Linux and 1e-8 on macOS), which ties the PEtab problem to the result
it reproduces.

## Results (recorded 2026-10-05, second run)

`scripts/run_gelain_2020_petab_reproduction.py` wrote
`data/benchmarks/gelain_2020_petab/results/` (`comparison.json`, `report.md`,
the PEtab directory and the COPASI file). Outcome: **`reproduced`**.

Simulation at FungMod's optimum: the worst |COPASI − FungMod| / sigma over all
96 measurements is 1.6e-8 and the objectives agree to 2e-8. The gate passes
by four orders of magnitude; the SBML export, the condition table and the
weight correction reproduce FungMod's compiled core.

Optimum: COPASI's local Levenberg-Marquardt fit from FungMod's optimum
(`3.976071899`) reaches `3.976071799`, a relative difference of 2.5e-8 against
the 0.1 percent tolerance, and the ten random starts reach 3.9768 to 4.0800
(none below the local fit). Every parameter agrees to better than 1e-4
relative, with `K_ind`, `kF` and `kB` on their lower bounds in both solvers.
FungMod's compiled core evaluates COPASI's best point to `3.976071724`
(relative difference 1.9e-8).

| Parameter | FungMod | COPASI best | relative difference |
| --- | --- | --- | --- |
| `k_h` | 0.01839 | 0.01839 | 5e-5 |
| `Kh` | 16.75 | 16.74 | 7e-5 |
| `Y` | 0.4146 | 0.4146 | 2e-5 |
| `kd` | 0.01985 | 0.01985 | 5e-5 |
| `K_ind` | 0.0100 (lower bound) | 0.0100 (lower bound) | 1e-14 |
| `qF` | 5.823 | 5.823 | 1e-6 |
| `kF` | 1.0e-6 (lower bound) | 1.0e-6 (lower bound) | 6e-7 |
| `qB` | 13.94 | 13.94 | 4e-5 |
| `kB` | 1.0e-6 (lower bound) | 1.0e-6 (lower bound) | 4e-11 |

### The first run and what it found

The first run (plan digest `a0f8abe9...`, same settings) was recorded with
outcome `copasi_improves`: at FungMod's then optimum (`4.030662656`) the
simulations agreed to 1.7e-8 of sigma, but COPASI's local fit reached 3.9803
and its best random start 3.9768, 1.3 percent lower, and FungMod evaluated
that point to the same objective (7e-9). The better optimum sat on three lower
bounds (`K_ind`, `kF`, `kB`) and along the `k_h`/`Kh` direction that stage A
and the Bayesian study had flagged as weakly determined. The difference was
the optimisers' stopping, not the simulators: FungMod's stage A fit was using
scipy's default finite-difference step, which differentiates the adaptive ODE
integrator's step noise and collapses the trust region. The criticism plan's
amendment 3 declares the step (`docs/gelain-model-criticism.md`), stage A was
re-run, and this study was re-run against the new reference fit. COPASI's
earlier best point (3.9768) is 1.9e-4 above FungMod's new optimum, so the
agreement is now symmetric: neither solver finds a lower point than the other
within the tolerance.

## What it is not

- Not biological validation, and not a blind or independent prediction.
- Not a statement that the optimum is unique or the parameters identified
  (see the criticism and Bayesian studies).
- Not a statement about the mechanisms M1 to M3.

## Reproducing it

```bash
pip install "fungmod[standards,copasi]"
python scripts/run_gelain_2020_petab_reproduction.py --output data/benchmarks/gelain_2020_petab/results
```

The run is deterministic (seeded starts, LSODA at the planned tolerances) and
takes about 90 seconds. `--starts` and `--seed` override the plan and are
recorded as deviations (`settings.as_planned` is then false).
