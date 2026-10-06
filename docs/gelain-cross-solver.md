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
`a0f8abe9561ad1936a2ef06055cd7af8a04cf4902008790d0a14c3cb58f3184a`,
pinned by `tests/test_gelain_petab.py`) fixes, before any COPASI run: the
sources and their digests (the criticism plan, the Bayesian plan, the
observations and the stage A `M0_baseline` primary fit that is FungMod's
optimum), the objective, the COPASI settings (importer, weight correction,
LSODA at relative tolerance 1e-9 and absolute tolerance 1e-12,
Levenberg-Marquardt, one local fit from FungMod's optimum and ten log-uniform
random starts with seed 20261005), two gates and three outcomes:

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
twice the recorded stage A cost (`4.030662656`, relative difference below
1e-9), which ties the PEtab problem to the result it reproduces.

## Results (recorded 2026-10-05)

`scripts/run_gelain_2020_petab_reproduction.py` wrote
`data/benchmarks/gelain_2020_petab/results/` (`comparison.json`, `report.md`,
the PEtab directory and the COPASI file). Outcome: **`copasi_improves`**.

Simulation at FungMod's optimum: the worst |COPASI − FungMod| / sigma over all
96 measurements is 1.7e-8 and the objectives agree to 5e-10. The gate passes
by four orders of magnitude; the SBML export, the condition table and the
weight correction reproduce FungMod's compiled core.

Optimum: COPASI's local Levenberg-Marquardt fit from FungMod's optimum reaches
3.9803 after 13 991 evaluations, and the ten random starts reach 3.9768 to
4.0800 (best 3.9768, start 2). FungMod's recorded optimum is 4.0307, so COPASI
improves on it by 1.3 percent, above the 0.1 percent tolerance. At COPASI's
best point FungMod's compiled core gives 3.97682321 against COPASI's
3.97682324 (relative difference 7e-9): the two solvers agree there too, so the
difference is the optimisers' stopping, not the simulators. FungMod's stage A
fit (`scipy.optimize.least_squares` in log space, five starts, default
tolerances) stopped 1.3 percent above the minimum COPASI finds.

| Parameter | FungMod | COPASI best | relative difference |
| --- | --- | --- | --- |
| `k_h` | 0.0127 | 0.0180 | 0.42 |
| `Kh` | 10.5 | 16.3 | 0.55 |
| `Y` | 0.372 | 0.406 | 0.093 |
| `kd` | 0.0179 | 0.0193 | 0.074 |
| `K_ind` | 0.0101 | 0.0100 (lower bound) | 0.0087 |
| `qF` | 6.88 | 5.91 | 0.14 |
| `kF` | 3.9e-5 | 1.0e-6 (lower bound) | 0.97 |
| `qB` | 16.0 | 14.1 | 0.12 |
| `kB` | 1.2e-6 | 1.0e-6 (lower bound) | 0.20 |

The better optimum sits on three lower bounds (`K_ind`, `kF`, `kB`) and moves
along the `k_h`/`Kh` direction that stage A and the Bayesian study already
flagged as weakly determined. None of this changes any scientific verdict by
itself: the criticism study's holdout comparisons are relative between models
fitted with the same optimiser, and the Bayesian study samples the posterior
rather than relying on the optimum. It does mean the stage A optimiser needs a
tighter stopping rule or a finishing step before its all-condition fits are
quoted as optima; that is the next task recorded in `progress.md`.

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
